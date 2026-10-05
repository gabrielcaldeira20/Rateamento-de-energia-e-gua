from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from cobrancas import services as cobrancas
from cobrancas.models import Cobranca
from core import fabrica
from core.services import numeros_painel
from despesas.forms import DespesaForm
from despesas.models import Despesa

JUN = date(2026, 6, 1)


class DespesaTests(TestCase):
    def test_outra_exige_texto(self):
        form = DespesaForm(data={"descricao": "X", "categoria": "OUTRA", "valor": "10", "data": "2026-06-05"})
        self.assertFalse(form.is_valid())
        self.assertIn("categoria_outra", form.errors)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Despesa.objects.create(descricao="X", categoria="OUTRA", valor=1, data=JUN, competencia=JUN)

    def test_competencia_vazia_usa_mes_da_data(self):
        form = DespesaForm(data={"descricao": "Cabos", "categoria": "MATERIAL", "valor": "187.50", "data": "2026-06-20"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().competencia, JUN)

    def test_competencia_informada_prevalece(self):
        form = DespesaForm(data={"descricao": "Conta", "categoria": "CONTA_ENERGIA", "valor": "2830",
                                 "data": "2026-07-02", "competencia": "2026-06"})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().competencia, JUN)

    def test_categorias_do_prototipo(self):
        rotulos = [r for _, r in Despesa._meta.get_field("categoria").choices]
        self.assertEqual(rotulos, ["Manutenção", "Material", "Conta de energia", "Folha de pagamento",
                                   "Combustível", "Documentos", "Limpeza", "Outra"])


class DespesaTelasTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())

    def test_criar_editar_filtrar_excluir(self):
        resp = self.client.post(reverse("despesas:nova"), {"descricao": "Reparo", "categoria": "OUTRA",
                                "categoria_outra": "Obra", "valor": "320", "data": "2026-06-10"})
        self.assertRedirects(resp, reverse("despesas:lista"))
        d = Despesa.objects.get()
        self.assertEqual(d.rotulo_categoria, "Obra")
        self.client.post(reverse("despesas:editar", args=[d.pk]), {"descricao": "Reparo", "categoria": "MANUTENCAO",
                         "valor": "350", "data": "2026-06-10", "competencia": "2026-06"})
        d.refresh_from_db()
        self.assertEqual((d.categoria, d.categoria_outra, d.valor), ("MANUTENCAO", "", Decimal("350.00")))
        resp = self.client.get(reverse("despesas:lista"), {"mes": "2026-06", "categoria": "MANUTENCAO"})
        self.assertEqual(len(resp.context["lista"]), 1)
        resp = self.client.get(reverse("despesas:lista"), {"categoria": "LIMPEZA"})
        self.assertEqual(len(resp.context["lista"]), 0)
        self.client.post(reverse("despesas:excluir", args=[d.pk]))
        self.assertFalse(Despesa.objects.exists())


class PainelTests(TestCase):
    def test_numeros_do_painel_por_competencia(self):
        ana = fabrica.associado("Ana")
        fabrica.associado("Inativo", ativo=False)
        mens = Cobranca.objects.create(associado=ana, tipo="MENSALIDADE", competencia=JUN, valor=Decimal("40"))
        energia = Cobranca.objects.create(associado=ana, tipo="ENERGIA", rede="SEDE", competencia=JUN,
                                          valor=Decimal("100"), vencimento=date(2026, 7, 10))
        velha = Cobranca.objects.create(associado=ana, tipo="ENERGIA", rede="SEDE", competencia=date(2026, 5, 1),
                                        valor=Decimal("60"), vencimento=date(2026, 6, 10))
        # Pagamento feito em julho de cobrança de junho conta em junho (competência).
        cobrancas.registrar_pagamento(energia.pk, Decimal("30"), date(2026, 7, 1))
        # Pagamento feito em junho de cobrança de maio não conta em junho.
        cobrancas.registrar_pagamento(velha.pk, Decimal("10"), date(2026, 6, 5))
        Despesa.objects.create(descricao="Cabos", categoria="MATERIAL", valor=Decimal("25"), data=JUN, competencia=JUN)

        n = numeros_painel(JUN, data_base=date(2026, 6, 20))
        self.assertEqual(n.a_receber, Decimal("110.00"))   # 40 + 70
        self.assertEqual(n.entradas, Decimal("30.00"))
        self.assertEqual(n.despesas, Decimal("25.00"))
        self.assertEqual(n.saldo, Decimal("5.00"))
        self.assertEqual(n.associados_ativos, 1)
        self.assertEqual(n.cobrancas_pendentes, 2)
        # Só a de maio venceu; a mensalidade não tem vencimento e nunca entra em atraso.
        self.assertEqual(n.em_atraso, Decimal("50.00"))
        self.assertEqual(n.qtd_em_atraso, 1)
        self.assertFalse(mens.em_atraso)

    def test_tela_do_painel(self):
        self.client.force_login(fabrica.tesoureiro())
        resp = self.client.get(reverse("core:painel"))
        self.assertContains(resp, "Total a receber")
        self.assertContains(resp, "Em atraso")
