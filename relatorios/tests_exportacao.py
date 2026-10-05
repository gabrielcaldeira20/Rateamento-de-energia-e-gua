"""Testes da exportação do relatório financeiro em CSV e PDF."""
import csv
import io
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from cobrancas import services as cobrancas
from cobrancas.models import Cobranca
from core import fabrica
from despesas.models import Despesa
from energia import services as energia

MAI, JUN, JUL = date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)


def brl(texto):
    """Converte '1.234,56' em Decimal."""
    return Decimal(texto.replace(".", "").replace(",", "."))


class ExportacaoTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())
        self.ana = fabrica.associado("Ana Souza", sede=True, poco=True)
        venc = date(2026, 7, 10)
        energia.fechar_energia("SEDE", JUN, Decimal("100.00"), 200, venc, {self.ana.pk: 1050})
        energia.fechar_energia("POCO", JUN, Decimal("50.00"), 100, venc, {self.ana.pk: 520})
        mens = Cobranca.objects.create(associado=self.ana, tipo="MENSALIDADE", competencia=MAI, valor=Decimal("1240.50"))
        cobrancas.registrar_pagamento(mens.pk, Decimal("1240.50"), date(2026, 6, 5))
        sede = Cobranca.objects.get(associado=self.ana, tipo="ENERGIA", rede="SEDE")
        cobrancas.registrar_pagamento(sede.pk, Decimal("30"), date(2026, 7, 2))
        Despesa.objects.create(descricao="Conta da concessionaria", categoria="CONTA_ENERGIA", valor=Decimal("25.10"),
                               data=date(2026, 7, 3), competencia=JUN)
        Despesa.objects.create(descricao="Cabos", categoria="MATERIAL", valor=Decimal("8.40"),
                               data=date(2026, 6, 20), competencia=JUN)

    def exportar(self, formato, regime, inicio, fim):
        return self.client.get(reverse("relatorios:exportar"),
                               {"formato": formato, "regime": regime, "inicio": inicio, "fim": fim})

    def resumo_da_tela(self, regime, inicio, fim):
        resp = self.client.get(reverse("relatorios:financeiro"),
                               {"modo": regime, "periodo": "custom", "inicio": inicio, "fim": fim})
        return resp.context["resumo"]

    def ler_csv(self, resp):
        conteudo = resp.content
        self.assertTrue(conteudo.startswith(b"\xef\xbb\xbf"), "CSV precisa de BOM")
        linhas = list(csv.reader(io.StringIO(conteudo.decode("utf-8-sig")), delimiter=";"))
        rotulados = {l[0]: l for l in linhas if l}
        return linhas, rotulados

    def test_total_do_csv_igual_ao_resumo_da_tela(self):
        casos = [
            ("pagamento", "2026-06", "2026-06"),
            ("competencia", "2026-06", "2026-06"),
            ("pagamento", "2026-05", "2026-07"),    # período personalizado
            ("competencia", "2026-05", "2026-07"),
        ]
        for regime, inicio, fim in casos:
            with self.subTest(regime=regime, inicio=inicio, fim=fim):
                resp = self.exportar("csv", regime, inicio, fim)
                self.assertEqual(resp.status_code, 200)
                self.assertIn("text/csv", resp["Content-Type"])
                self.assertIn("attachment;", resp["Content-Disposition"])
                linhas, r = self.ler_csv(resp)
                tela = self.resumo_da_tela(regime, inicio, fim)
                self.assertEqual(brl(r["Entradas"][1]), tela.entradas)
                self.assertEqual(brl(r["Despesas"][1]), tela.despesas)
                self.assertEqual(brl(r["Saldo"][1]), tela.saldo)
                self.assertEqual(brl(r["Taxa de disponibilidade"][1]), tela.disponibilidade)
                self.assertEqual(brl(r["Total de entradas"][4]), tela.entradas)
                self.assertEqual(brl(r["Total de despesas"][4]), tela.despesas)
                # A soma das linhas das tabelas bate com os totais.
                ini_e = linhas.index(["Data", "Associado", "Tipo", "Competência", "Valor (R$)"]) + 1
                fim_e = next(i for i, l in enumerate(linhas) if l and l[0] == "Total de entradas")
                self.assertEqual(sum((brl(l[4]) for l in linhas[ini_e:fim_e]), Decimal("0")), tela.entradas)

    def test_csv_tem_cabecalho_e_formato_brasileiro(self):
        resp = self.exportar("csv", "pagamento", "2026-06", "2026-06")
        linhas, r = self.ler_csv(resp)
        self.assertEqual(r["Regime"][1], "Por data de pagamento")
        self.assertEqual(r["Período"][1], "jun/2026 a jun/2026")
        self.assertIn("Gerado em", r)
        self.assertEqual(r["Entradas"][1], "1.240,50")
        self.assertIn(["05/06/2026", "Ana Souza", "Mensalidade", "mai/2026", "1.240,50"], linhas)
        self.assertIn('filename="relatorio-financeiro-pagamento-2026-06_2026-06.csv"', resp["Content-Disposition"])

    def test_pdf_com_dados(self):
        resp = self.exportar("pdf", "competencia", "2026-05", "2026-07")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn(b"Ana Souza", resp.content)
        self.assertIn(b"1.240,50", resp.content)
        self.assertIn(b"Cabos", resp.content)
        self.assertIn(b"mai/2026 a jul/2026", resp.content)

    def test_pdf_sem_dados(self):
        resp = self.exportar("pdf", "pagamento", "2020-01", "2020-03")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertIn(b"Nenhum registro no per", resp.content)
        self.assertIn(b"jan/2020 a mar/2020", resp.content)

    def test_formato_invalido(self):
        self.assertEqual(self.exportar("xls", "pagamento", "2026-06", "2026-06").status_code, 400)

    def test_exportacao_exige_login(self):
        self.client.logout()
        for formato in ("csv", "pdf"):
            resp = self.exportar(formato, "pagamento", "2026-06", "2026-06")
            self.assertEqual(resp.status_code, 302)
            self.assertTrue(resp.url.startswith(reverse("login")))
