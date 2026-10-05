from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from associados import services
from associados.forms import AssociadoForm
from associados.models import Associado
from core import fabrica


def dados_form(**extra):
    base = {
        "nome": "João", "contato": "(38) 98888-1111", "endereco": "Sítio Boa Vista",
        "valor_mensalidade": "40.00",
    }
    base.update(extra)
    return base


class FormularioTests(TestCase):
    def test_ativar_rede_exige_leitura_inicial(self):
        form = AssociadoForm(data=dados_form(rede_sede="on", padrao_ligado_sede="on"))
        self.assertFalse(form.is_valid())
        self.assertIn("leitura_inicial_sede", form.errors)
        form = AssociadoForm(data=dados_form(rede_sede="on", padrao_ligado_sede="on", leitura_inicial_sede="1200"))
        self.assertTrue(form.is_valid(), form.errors)

    def test_contato_obrigatorio(self):
        form = AssociadoForm(data=dados_form(contato=""))
        self.assertFalse(form.is_valid())
        self.assertIn("contato", form.errors)

    def test_sem_rede_desliga_padrao(self):
        form = AssociadoForm(data=dados_form(padrao_ligado_poco="on"))
        self.assertTrue(form.is_valid())
        self.assertFalse(form.save().padrao_ligado_poco)

    def test_banco_tambem_exige_leitura_inicial(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Associado.objects.create(nome="X", contato="1", rede_poco=True)


class ServicosTests(TestCase):
    def setUp(self):
        self.maria = fabrica.associado("Maria", sede=True, agua_ligada=True)
        self.joao = fabrica.associado("João", sede=False, poco=True)
        self.sem_padrao = fabrica.associado("Ana", sede=True, padrao_ligado_sede=False)
        self.inativo = fabrica.associado("Pedro", sede=True, ativo=False)

    def test_filtros(self):
        self.assertEqual(set(services.filtrar(rede="sede")), {self.maria, self.sem_padrao})
        self.assertEqual(list(services.filtrar(agua="ligada")), [self.maria])
        self.assertEqual(list(services.filtrar(status="inativos")), [self.inativo])
        self.assertEqual(list(services.filtrar(busca="jo")), [self.joao])

    def test_elegiveis_exigem_ativo_rede_e_padrao(self):
        self.assertEqual(list(services.elegiveis_energia("SEDE")), [self.maria])
        self.assertEqual(list(services.elegiveis_energia("POCO")), [self.joao])

    def test_inativar_nao_apaga(self):
        services.definir_ativo(self.maria, False)
        self.assertTrue(Associado.objects.filter(pk=self.maria.pk, ativo=False).exists())


class TelasTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())

    def test_cadastro_edicao_inativar_reativar(self):
        resp = self.client.post(reverse("associados:novo"), dados_form(rede_sede="on", padrao_ligado_sede="on", leitura_inicial_sede="10"))
        self.assertRedirects(resp, reverse("associados:lista"))
        a = Associado.objects.get(nome="João")
        resp = self.client.post(reverse("associados:editar", args=[a.pk]), dados_form(nome="João Pereira"))
        self.assertRedirects(resp, reverse("associados:lista"))
        a.refresh_from_db()
        self.assertEqual(a.nome, "João Pereira")
        self.client.post(reverse("associados:inativar", args=[a.pk]))
        a.refresh_from_db()
        self.assertFalse(a.ativo)
        self.client.post(reverse("associados:reativar", args=[a.pk]))
        a.refresh_from_db()
        self.assertTrue(a.ativo)

    def test_lista_e_detalhe(self):
        a = fabrica.associado("Maria")
        self.assertContains(self.client.get(reverse("associados:lista")), "Maria")
        self.assertContains(self.client.get(reverse("associados:detalhe", args=[a.pk])), "Histórico de cobranças")

    def test_exige_login(self):
        self.client.logout()
        resp = self.client.get(reverse("associados:lista"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.url)
