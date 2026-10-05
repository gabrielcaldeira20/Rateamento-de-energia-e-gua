from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cobrancas import services
from cobrancas.models import Cobranca, MovimentoCredito, Pagamento, StatusCobranca, TipoCobranca
from core import fabrica
from core.models import Configuracao

JUN = date(2026, 6, 1)
DIA = date(2026, 6, 15)


def cobranca(associado, valor="100.00", tipo=TipoCobranca.MENSALIDADE, competencia=JUN, **extra):
    return Cobranca.objects.create(associado=associado, tipo=tipo, competencia=competencia, valor=Decimal(valor), **extra)


class GeracaoMensalTests(TestCase):
    def setUp(self):
        self.com_agua = fabrica.associado("Ana", agua_ligada=True, valor_mensalidade=Decimal("40.00"))
        self.sem_agua = fabrica.associado("Bruno", valor_mensalidade=Decimal("15.00"))
        self.inativo = fabrica.associado("Caio", ativo=False, agua_ligada=True)

    def test_cria_mensalidade_e_agua_para_ativos(self):
        r = services.gerar_mensais(JUN)
        self.assertEqual((r.criadas, r.existentes), (3, 0))
        self.assertEqual(r.total_criado, Decimal("90.00"))  # 40 + 35 de água + 15
        agua = Cobranca.objects.get(associado=self.com_agua, tipo=TipoCobranca.AGUA)
        self.assertEqual(agua.valor, Decimal("35.00"))
        self.assertEqual(agua.rede, "NENHUMA")
        self.assertIsNone(agua.vencimento)
        self.assertFalse(Cobranca.objects.filter(associado=self.inativo).exists())

    def test_gerar_duas_vezes_nao_duplica(self):
        services.gerar_mensais(JUN)
        r = services.gerar_mensais(JUN)
        self.assertEqual((r.criadas, r.existentes), (0, 3))
        self.assertEqual(Cobranca.objects.count(), 3)

    def test_valor_copiado_na_criacao(self):
        services.gerar_mensais(JUN)
        config = Configuracao.atual()
        config.valor_agua = Decimal("50.00")
        config.save()
        self.com_agua.valor_mensalidade = Decimal("99.00")
        self.com_agua.save()
        self.assertEqual(Cobranca.objects.get(associado=self.com_agua, tipo="AGUA").valor, Decimal("35.00"))
        self.assertEqual(Cobranca.objects.get(associado=self.com_agua, tipo="MENSALIDADE").valor, Decimal("40.00"))


class PagamentoTests(TestCase):
    def setUp(self):
        self.ana = fabrica.associado("Ana")
        self.c = cobranca(self.ana, "100.00")

    def test_pagamento_parcial(self):
        r = services.registrar_pagamento(self.c.pk, Decimal("30.00"), DIA, "dinheiro")
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, StatusCobranca.PARCIAL)
        self.assertEqual(self.c.saldo, Decimal("70.00"))
        self.assertEqual(r.credito_gerado, Decimal("0"))
        services.registrar_pagamento(self.c.pk, Decimal("70.00"), DIA)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, StatusCobranca.PAGA)

    def test_pagamento_a_maior_gera_credito(self):
        r = services.registrar_pagamento(self.c.pk, Decimal("130.00"), DIA)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, StatusCobranca.PAGA)
        self.assertEqual(self.c.valor_pago, Decimal("100.00"))
        self.assertEqual(r.pagamento.valor, Decimal("130.00"))
        self.assertEqual(r.credito_gerado, Decimal("30.00"))
        self.assertEqual(MovimentoCredito.objects.get().valor, Decimal("30.00"))

    def test_credito_so_desconta_saldo_exibido_e_nao_quita(self):
        services.registrar_pagamento(self.c.pk, Decimal("130.00"), DIA)
        outra = cobranca(self.ana, "50.00", competencia=date(2026, 7, 1))
        self.assertEqual(services.saldos_devedores([self.ana.pk])[self.ana.pk], Decimal("20.00"))
        outra.refresh_from_db()
        self.assertEqual(outra.status, StatusCobranca.PENDENTE)  # nada quitado sozinho
        self.assertEqual(services.credito_disponivel(self.ana), Decimal("0"))
        outra.delete()
        self.assertEqual(services.saldos_devedores([self.ana.pk])[self.ana.pk], Decimal("0"))
        self.assertEqual(services.credito_disponivel(self.ana), Decimal("30.00"))

    def test_valor_zero_e_cobranca_paga_sao_recusados(self):
        with self.assertRaises(services.PagamentoInvalido):
            services.registrar_pagamento(self.c.pk, Decimal("0"), DIA)
        services.registrar_pagamento(self.c.pk, Decimal("100.00"), DIA)
        with self.assertRaises(services.PagamentoInvalido):
            services.registrar_pagamento(self.c.pk, Decimal("1.00"), DIA)


class BaixaEmLoteTests(TestCase):
    def setUp(self):
        self.ana = fabrica.associado("Ana")
        self.parcial = cobranca(self.ana, "100.00")
        services.registrar_pagamento(self.parcial.pk, Decimal("40.00"), DIA)
        self.cheia = cobranca(self.ana, "35.00", tipo=TipoCobranca.AGUA)
        self.paga = cobranca(self.ana, "10.00", competencia=date(2026, 5, 1))
        services.registrar_pagamento(self.paga.pk, Decimal("10.00"), DIA)

    def test_paga_pelo_saldo_restante_com_mesmo_lote(self):
        qtd, total, lote = services.baixar_em_lote([self.parcial.pk, self.cheia.pk, self.paga.pk], DIA)
        self.assertEqual(qtd, 2)
        self.assertEqual(total, Decimal("95.00"))  # 60 restantes + 35
        pagamentos = Pagamento.objects.filter(lote=lote)
        self.assertEqual(sorted(p.valor for p in pagamentos), [Decimal("35.00"), Decimal("60.00")])
        self.assertTrue(all(p.data == DIA for p in pagamentos))
        for c in (self.parcial, self.cheia):
            c.refresh_from_db()
            self.assertEqual(c.status, StatusCobranca.PAGA)
            self.assertEqual(c.valor_pago, c.valor)
        self.assertFalse(MovimentoCredito.objects.exists())  # saldo restante, nunca a maior

    def test_baixa_em_lote_e_atomica(self):
        original = services._registrar
        chamadas = []

        def falhar_na_segunda(*args, **kwargs):
            chamadas.append(1)
            if len(chamadas) == 2:
                raise RuntimeError("falha simulada")
            return original(*args, **kwargs)

        with mock.patch.object(services, "_registrar", side_effect=falhar_na_segunda):
            with self.assertRaises(RuntimeError):
                services.baixar_em_lote([self.parcial.pk, self.cheia.pk], DIA)
        self.parcial.refresh_from_db()
        self.cheia.refresh_from_db()
        self.assertEqual(self.parcial.valor_pago, Decimal("40.00"))
        self.assertEqual(self.cheia.status, StatusCobranca.PENDENTE)
        self.assertFalse(Pagamento.objects.filter(lote__isnull=False).exists())


class TelasTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())
        self.ana = fabrica.associado("Ana", agua_ligada=True)

    def test_gerar_pagar_e_lote_pela_tela(self):
        resp = self.client.post(reverse("cobrancas:gerar_mensais"), {"competencia": "2026-06"})
        self.assertRedirects(resp, reverse("cobrancas:lista"))
        self.assertEqual(Cobranca.objects.count(), 2)
        resp = self.client.get(reverse("cobrancas:lista"))
        self.assertContains(resp, "Ana")
        mens = Cobranca.objects.get(tipo="MENSALIDADE")
        self.client.post(reverse("cobrancas:pagar", args=[mens.pk]), {"valor": "10.00", "data": "2026-06-15", "observacao": ""})
        mens.refresh_from_db()
        self.assertEqual(mens.status, StatusCobranca.PARCIAL)
        self.client.post(reverse("cobrancas:lote"), {"ids": [str(c.pk) for c in Cobranca.objects.all()]})
        self.assertEqual(Cobranca.objects.filter(status=StatusCobranca.PAGA).count(), 2)

    def test_filtros_da_lista(self):
        services.gerar_mensais(JUN)
        resp = self.client.get(reverse("cobrancas:lista"), {"tipo": "AGUA", "mes": "2026-06", "status": "todos"})
        self.assertEqual(len(resp.context["lista"]), 1)

    def test_saldo_aparece_na_lista_de_associados(self):
        cobranca(self.ana, "80.00")
        resp = self.client.get(reverse("associados:lista"))
        self.assertContains(resp, "R$ 80,00")
