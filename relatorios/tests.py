from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cobrancas import services as cobrancas
from cobrancas.models import Cobranca
from core import fabrica
from despesas.models import Despesa
from energia import services as energia
from relatorios import services

MAI, JUN, JUL = date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)


class PeriodoTests(TestCase):
    def test_presets(self):
        self.assertEqual(services.resolver_periodo("atual", base=JUN), (JUN, JUN))
        self.assertEqual(services.resolver_periodo("3m", base=JUN), (date(2026, 4, 1), JUN))
        self.assertEqual(services.resolver_periodo("6m", base=JUN), (date(2026, 1, 1), JUN))
        self.assertEqual(services.resolver_periodo("custom", JUL, MAI, base=JUN), (MAI, JUL))
        self.assertEqual(services.resolver_periodo("custom", None, None, base=JUN), (date(2026, 1, 1), JUN))


class RelatorioTests(TestCase):
    def setUp(self):
        self.ana = fabrica.associado("Ana", sede=True, poco=True)
        self.assoc = fabrica.associado("Associação", e_associacao=True)
        venc = date(2026, 7, 10)
        energia.fechar_energia("SEDE", JUN, Decimal("100.00"), 200, venc, {self.ana.pk: 1050, self.assoc.pk: 1050})
        energia.fechar_energia("POCO", JUN, Decimal("50.00"), 100, venc, {self.ana.pk: 520})
        mens = Cobranca.objects.create(associado=self.ana, tipo="MENSALIDADE", competencia=MAI, valor=Decimal("40"))
        # Mensalidade de maio paga em junho; energia de junho paga em julho.
        cobrancas.registrar_pagamento(mens.pk, Decimal("40"), date(2026, 6, 5))
        sede = Cobranca.objects.get(associado=self.ana, tipo="ENERGIA", rede="SEDE")
        cobrancas.registrar_pagamento(sede.pk, Decimal("30"), date(2026, 7, 2))
        # Despesa com data em julho e competência em junho.
        Despesa.objects.create(descricao="Conta", categoria="CONTA_ENERGIA", valor=Decimal("25"),
                               data=date(2026, 7, 3), competencia=JUN)

    def test_disponibilidade_separada_soma_por_rede_e_ignora_associacao(self):
        r = services.resumo_periodo(JUN, JUN)
        self.assertEqual(r.disponibilidade, Decimal("10.00"))  # 5 da Sede + 5 do Poço, Associação isenta
        self.assertEqual(services.resumo_periodo(MAI, MAI).disponibilidade, Decimal("0.00"))

    def test_modo_por_data_de_pagamento(self):
        jun = services.resumo_periodo(JUN, JUN, "pagamento")
        self.assertEqual((jun.entradas, jun.despesas, jun.saldo), (Decimal("40.00"), Decimal("0.00"), Decimal("40.00")))
        jul = services.resumo_periodo(JUL, JUL, "pagamento")
        self.assertEqual((jul.entradas, jul.despesas), (Decimal("30.00"), Decimal("25.00")))

    def test_modo_por_competencia(self):
        jun = services.resumo_periodo(JUN, JUN, "competencia")
        self.assertEqual((jun.entradas, jun.despesas, jun.saldo), (Decimal("30.00"), Decimal("25.00"), Decimal("5.00")))
        self.assertEqual(services.resumo_periodo(MAI, MAI, "competencia").entradas, Decimal("40.00"))

    def test_serie_mensal(self):
        serie = services.serie_mensal(MAI, JUL, "pagamento")
        self.assertEqual([s["mes"] for s in serie], ["mai/2026", "jun/2026", "jul/2026"])
        self.assertEqual([s["entradas"] for s in serie], [Decimal("0.00"), Decimal("40"), Decimal("30")])
        self.assertEqual([s["despesas"] for s in serie], [Decimal("0.00"), Decimal("0.00"), Decimal("25")])

    def test_tela(self):
        self.client.force_login(fabrica.tesoureiro())
        resp = self.client.get(reverse("relatorios:financeiro"),
                               {"modo": "competencia", "periodo": "custom", "inicio": "2026-06", "fim": "2026-06"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["resumo"].disponibilidade, Decimal("10.00"))
        self.assertContains(resp, "dados-grafico")
        # O botão bloqueado deu lugar aos botões de exportação, com regime e período da tela.
        self.assertNotContains(resp, "Disponível no plano Avançado")
        self.assertContains(resp, "formato=pdf&amp;regime=competencia&amp;inicio=2026-06&amp;fim=2026-06")
        self.assertContains(resp, "formato=csv&amp;regime=competencia&amp;inicio=2026-06&amp;fim=2026-06")
        self.assertContains(resp, "chart.umd.min.js")
