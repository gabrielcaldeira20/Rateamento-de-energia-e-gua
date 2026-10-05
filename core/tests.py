from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core import utils
from core.models import Configuracao


class UtilsTests(TestCase):
    def test_formatar_brl(self):
        self.assertEqual(utils.formatar_brl(Decimal("1234.5")), "R$ 1.234,50")
        self.assertEqual(utils.formatar_brl(Decimal("0.005")), "R$ 0,01")
        self.assertEqual(utils.formatar_brl(Decimal("-12")), "R$ -12,00")

    def test_arredondamento_meio_para_cima(self):
        self.assertEqual(utils.arredondar(Decimal("2.345")), Decimal("2.35"))
        self.assertEqual(utils.arredondar(Decimal("2.344")), Decimal("2.34"))

    def test_meses(self):
        self.assertEqual(utils.somar_meses(date(2026, 12, 15), 1), date(2027, 1, 1))
        self.assertEqual(utils.somar_meses(date(2026, 1, 1), -1), date(2025, 12, 1))
        self.assertEqual(utils.mes_label(date(2026, 6, 1)), "jun/2026")
        self.assertEqual(utils.parse_mes("2026-06"), date(2026, 6, 1))
        self.assertIsNone(utils.parse_mes("lixo"))
        self.assertEqual(len(utils.meses_entre(date(2026, 1, 1), date(2026, 6, 1))), 6)


class ConfiguracaoTests(TestCase):
    def test_linha_unica_com_padroes(self):
        c = Configuracao.atual()
        self.assertEqual(c.pk, 1)
        self.assertEqual(c.taxa_disponibilidade, Decimal("5.00"))
        self.assertEqual(c.limite_kwh_multa, 100)
        self.assertEqual(c.percentual_multa, Decimal("10.00"))
        outra = Configuracao(chave_pix="x")
        outra.save()
        self.assertEqual(Configuracao.objects.count(), 1)


class LoginTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("tesoureiro", password="senha-forte-123")

    def test_sem_sessao_redireciona_para_login(self):
        resp = self.client.get(reverse("core:painel"))
        self.assertRedirects(resp, f"{reverse('login')}?next=/")

    def test_login_real_com_senha_errada_falha(self):
        resp = self.client.post(reverse("login"), {"username": "tesoureiro", "password": "errada"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "incorretos")

    def test_login_e_configuracoes(self):
        self.client.post(reverse("login"), {"username": "tesoureiro", "password": "senha-forte-123"})
        resp = self.client.get(reverse("core:configuracoes"))
        self.assertEqual(resp.status_code, 200)
        resp = self.client.post(reverse("core:configuracoes"), {
            "nome_associacao": "ASV", "chave_pix": "pix@asv.org", "taxa_disponibilidade": "6.00",
            "valor_agua": "35.00", "limite_kwh_multa": "100", "percentual_multa": "10",
        })
        self.assertRedirects(resp, reverse("core:configuracoes"))
        self.assertEqual(Configuracao.atual().chave_pix, "pix@asv.org")
        self.assertEqual(Configuracao.atual().taxa_disponibilidade, Decimal("6.00"))

    def test_menu_mostra_itens_bloqueados_sem_perfis(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("core:painel"))
        self.assertContains(resp, "PIX automático")
        self.assertContains(resp, "Histórico de ligações")
        self.assertNotContains(resp, "Perfis de usuário")
