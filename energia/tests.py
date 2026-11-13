from datetime import date
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from cobrancas.models import Cobranca, TipoCobranca
from core import fabrica
from energia import services
from energia.models import FechamentoEnergia, Leitura

JUN = date(2026, 6, 1)


class CalculosTests(TestCase):
    def test_fator_com_seis_casas(self):
        self.assertEqual(services.calcular_fator(Decimal("1850.00"), 2100), Decimal("0.880952"))

    def test_valor_arredonda_meio_para_cima(self):
        a = fabrica.associado("A")
        # fator 0,125: 1 kWh vale 0,125, que arredonda para 0,13 (e não 0,12).
        rateio = services.calcular_rateio("SEDE", JUN, Decimal("1.00"), 8, {a.pk: 1001})
        self.assertEqual(rateio.linhas[0].valor_energia, Decimal("0.13"))

    def test_soma_dos_valores_individuais_bate_com_a_conta(self):
        leituras = {}
        for i in range(7):
            a = fabrica.associado(f"A{i}")
            leituras[a.pk] = 1000 + 37 + i * 13
        rateio = services.calcular_rateio("SEDE", JUN, Decimal("1850.00"), 2100, leituras)
        self.assertEqual(rateio.soma_energia, sum(l.valor_energia for l in rateio.linhas))
        # Energia rateada mais a perda reconstituem a conta, a menos de meio centavo por linha.
        diferenca = abs(rateio.soma_energia + rateio.perda_valor - Decimal("1850.00"))
        self.assertLessEqual(diferenca, Decimal("0.005") * (len(rateio.linhas) + 1))
        self.assertEqual(rateio.perda_kwh, 2100 - rateio.soma_consumo)

    def test_vencimento_padrao_dia_10_do_mes_seguinte(self):
        self.assertEqual(services.vencimento_padrao(JUN), date(2026, 7, 10))
        self.assertEqual(services.vencimento_padrao(date(2026, 12, 1)), date(2027, 1, 10))


class FechamentoTests(TestCase):
    def setUp(self):
        self.a = fabrica.associado("Ana")                       # só Sede
        self.b = fabrica.associado("Bruno", sede=True, poco=True)  # Sede e Poço
        self.assoc = fabrica.associado("Associação", e_associacao=True)
        self.venc = date(2026, 7, 10)

    def fechar_sede(self, **leituras):
        valores = {self.a.pk: 1100, self.b.pk: 1101, self.assoc.pk: 1020}
        valores.update(leituras)
        return services.fechar_energia("SEDE", JUN, Decimal("210.00"), 250, self.venc, valores)

    def test_rateio_disponibilidade_e_multa(self):
        r = self.fechar_sede()
        self.assertEqual(r.fechamento.fator, Decimal("0.840000"))
        self.assertEqual(r.fechamento.perda_kwh, 29)
        self.assertEqual(r.fechamento.perda_valor, Decimal("24.36"))
        energia = {c.associado_id: c for c in Cobranca.objects.filter(tipo=TipoCobranca.ENERGIA)}
        self.assertEqual(energia[self.a.pk].valor, Decimal("89.00"))          # 100 kWh x 0,84 + 5
        self.assertEqual(energia[self.a.pk].valor_disponibilidade, Decimal("5.00"))
        self.assertEqual(energia[self.b.pk].valor, Decimal("89.84"))          # 101 kWh x 0,84 + 5
        self.assertEqual(energia[self.assoc.pk].valor, Decimal("16.80"))      # sem taxa
        self.assertEqual(energia[self.assoc.pk].valor_disponibilidade, Decimal("0.00"))
        self.assertEqual(energia[self.a.pk].vencimento, self.venc)
        self.assertEqual(energia[self.a.pk].rede, "SEDE")

    def test_multa_100_kwh_nao_gera_e_101_gera(self):
        self.fechar_sede()
        multas = Cobranca.objects.filter(tipo=TipoCobranca.MULTA)
        self.assertFalse(multas.filter(associado=self.a).exists())  # exatamente 100 kWh
        multa = multas.get(associado=self.b)                          # 101 kWh
        # 10% de 84,84 (energia sem a taxa de disponibilidade) = 8,484, arredonda para 8,48.
        self.assertEqual(multa.valor, Decimal("8.48"))
        self.assertEqual(multa.rede, "SEDE")
        self.assertEqual(multa.vencimento, self.venc)
        self.assertEqual(multa.fechamento.pk, FechamentoEnergia.objects.get().pk)

    def test_multa_usa_limite_e_percentual_da_configuracao(self):
        from core.models import Configuracao
        config = Configuracao.atual()
        config.limite_kwh_multa, config.percentual_multa = 50, Decimal("20")
        config.save()
        self.fechar_sede()
        self.assertEqual(Cobranca.objects.get(tipo=TipoCobranca.MULTA, associado=self.a).valor, Decimal("16.80"))

    def test_disponibilidade_10_reais_com_duas_redes_e_zero_para_associacao(self):
        self.fechar_sede()
        services.fechar_energia("POCO", JUN, Decimal("100.00"), 100, self.venc, {self.b.pk: 550})
        def total_disp(associado):
            return sum(c.valor_disponibilidade for c in Cobranca.objects.filter(associado=associado))
        self.assertEqual(total_disp(self.b), Decimal("10.00"))
        self.assertEqual(total_disp(self.a), Decimal("5.00"))
        self.assertEqual(total_disp(self.assoc), Decimal("0.00"))
        self.assertEqual(Cobranca.objects.get(associado=self.b, rede="POCO", tipo="ENERGIA").valor, Decimal("55.00"))

    def test_fechamento_duplicado_bloqueado(self):
        self.fechar_sede()
        with self.assertRaises(services.FechamentoInvalido):
            self.fechar_sede()
        self.assertEqual(FechamentoEnergia.objects.count(), 1)

    def test_leitura_menor_que_anterior_bloqueada_e_nada_gravado(self):
        leituras = {self.a.pk: 999, self.b.pk: 1101, self.assoc.pk: 1020}
        with self.assertRaises(services.FechamentoInvalido) as ctx:
            services.fechar_energia("SEDE", JUN, Decimal("210.00"), 250, self.venc, leituras)
        self.assertIn("menor", ctx.exception.erros[0])
        self.assertEqual(FechamentoEnergia.objects.count(), 0)
        self.assertEqual(Cobranca.objects.count(), 0)

    def test_leitura_nao_preenchida_bloqueada(self):
        with self.assertRaises(services.FechamentoInvalido):
            services.fechar_energia("SEDE", JUN, Decimal("210.00"), 250, self.venc, {self.a.pk: 1100, self.b.pk: None})
        self.assertEqual(Leitura.objects.count(), 0)

    def test_leitura_zerada_e_perda_negativa_so_avisam(self):
        leituras = {self.a.pk: 1000, self.b.pk: 1300, self.assoc.pk: 1000}
        rateio = services.calcular_rateio("SEDE", JUN, Decimal("210.00"), 250, leituras)
        self.assertEqual(rateio.erros, [])
        self.assertEqual(len(rateio.avisos), 2)
        self.assertTrue(rateio.pode_confirmar)
        r = services.fechar_energia("SEDE", JUN, Decimal("210.00"), 250, self.venc, leituras)
        self.assertEqual(r.fechamento.perda_kwh, -50)
        # Associação com consumo zero não recebe cobrança de valor zero; Ana paga só a taxa.
        self.assertFalse(Cobranca.objects.filter(associado=self.assoc).exists())
        self.assertEqual(Cobranca.objects.get(associado=self.a).valor, Decimal("5.00"))
        self.assertEqual(Leitura.objects.count(), 3)

    def test_leitura_anterior_vem_do_ultimo_fechamento(self):
        self.assertEqual(services.leitura_anterior(self.a, "SEDE"), 1000)
        self.fechar_sede()
        self.assertEqual(services.leitura_anterior(self.a, "SEDE"), 1100)
        self.assertEqual(services.leitura_anterior(self.b, "POCO"), 500)

    def test_leituras_anteriores_em_lote_igual_a_consulta_individual(self):
        associados = [self.a, self.b, self.assoc]

        def conferir():
            for rede in ("SEDE", "POCO"):
                esperado = {a.pk: services.leitura_anterior(a, rede) for a in associados}
                with self.assertNumQueries(1):
                    self.assertEqual(services.leituras_anteriores(associados, rede), esperado)

        conferir()          # sem fechamento: leitura inicial do cadastro
        self.fechar_sede()
        conferir()          # depois do fechamento: última leitura gravada

    def test_rateio_nao_faz_uma_consulta_por_associado(self):
        """O número de consultas do rateio não cresce com a quantidade de associados."""
        def consultas():
            from django.db import connection
            from django.test.utils import CaptureQueriesContext
            with CaptureQueriesContext(connection) as ctx:
                services.calcular_rateio("SEDE", JUN, Decimal("210.00"), 250, {})
            return len(ctx.captured_queries)

        from core.models import Configuracao
        Configuracao.atual()  # a primeira chamada cria a configuração; fica fora da contagem
        antes = consultas()
        for i in range(10):
            fabrica.associado(f"Extra {i}")
        self.assertEqual(consultas(), antes)

    def test_fechamento_e_atomico(self):
        original = Cobranca.objects.create

        def falhar_na_multa(**kwargs):
            if kwargs.get("tipo") == TipoCobranca.MULTA:
                raise RuntimeError("falha simulada")
            return original(**kwargs)

        with mock.patch.object(Cobranca.objects, "create", side_effect=falhar_na_multa):
            with self.assertRaises(RuntimeError):
                self.fechar_sede()
        self.assertEqual(FechamentoEnergia.objects.count(), 0)
        self.assertEqual(Leitura.objects.count(), 0)
        self.assertEqual(Cobranca.objects.count(), 0)


class TelasTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())
        self.a = fabrica.associado("Ana")

    def test_fluxo_em_tres_passos(self):
        resp = self.client.post(reverse("energia:passo1"), {
            "rede": "SEDE", "competencia": "2026-06", "vencimento": "2026-07-10",
            "valor_total": "84.00", "kwh_total": "100",
        })
        self.assertRedirects(resp, reverse("energia:passo2"))
        resp = self.client.get(reverse("energia:passo2"))
        self.assertContains(resp, "Ana")
        self.client.post(reverse("energia:passo2"), {f"leitura_{self.a.pk}": ""})
        resp = self.client.get(reverse("energia:passo3"))
        self.assertContains(resp, "não preenchida")
        self.assertContains(resp, "disabled")
        self.client.post(reverse("energia:passo2"), {f"leitura_{self.a.pk}": "1100"})
        resp = self.client.get(reverse("energia:passo3"))
        self.assertContains(resp, "Confirmar fechamento")
        resp = self.client.post(reverse("energia:passo3"))
        self.assertRedirects(resp, reverse("energia:concluido"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("energia:concluido")), "Mês fechado")
        self.assertEqual(Cobranca.objects.get().valor, Decimal("89.00"))

    def test_passo1_bloqueia_mes_ja_fechado(self):
        services.fechar_energia("SEDE", JUN, Decimal("84.00"), 100, date(2026, 7, 10), {self.a.pk: 1100})
        resp = self.client.post(reverse("energia:passo1"), {
            "rede": "SEDE", "competencia": "2026-06", "vencimento": "2026-07-10",
            "valor_total": "84.00", "kwh_total": "100",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Já existe fechamento")


class LerInteiroTests(TestCase):
    def test_entradas_validas_e_invalidas(self):
        from energia.views import ler_inteiro
        casos = {
            "1520": 1520, " 1520 ": 1520, "1520,0": 1520, "0": 0,
            "": None, None: None, "-3": None, "abc": None, "NaN": None, "Infinity": None,
        }
        for texto, esperado in casos.items():
            self.assertEqual(ler_inteiro(texto), esperado, texto)
