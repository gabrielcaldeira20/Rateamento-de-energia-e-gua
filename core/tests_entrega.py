"""Testes da fase de entrega: comandos administrativos e proteção por login."""
import csv
import io
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from associados.models import Associado
from cobrancas.models import Cobranca
from core import fabrica

RAIZ = Path(__file__).resolve().parent.parent


class ComandosTests(TestCase):
    def setUp(self):
        self.pasta = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.pasta, ignore_errors=True)

    def test_importar_planilhas_de_exemplo_e_nao_duplicar(self):
        saida = io.StringIO()
        call_command("importar_planilhas", str(RAIZ / "docs" / "exemplo_associados.csv"), stdout=saida)
        self.assertIn("Criados 3", saida.getvalue())
        maria = Associado.objects.get(nome="Maria Rodrigues")
        self.assertEqual(maria.leitura_inicial_sede, 1037)
        self.assertEqual(maria.valor_mensalidade, Decimal("40.00"))
        self.assertTrue(maria.agua_ligada)
        self.assertFalse(maria.rede_poco)
        self.assertTrue(Associado.objects.get(nome__startswith="Associação").e_associacao)
        call_command("importar_planilhas", str(RAIZ / "docs" / "exemplo_associados.csv"), stdout=io.StringIO())
        self.assertEqual(Associado.objects.count(), 3)

    def test_importar_com_erro_nao_grava_nada(self):
        arquivo = self.pasta / "ruim.csv"
        arquivo.write_text("nome;contato;rede_sede\nAna;(38) 9999-0000;sim\nBia;(38) 9999-1111;não\n", encoding="utf-8")
        with self.assertRaises(CommandError):
            call_command("importar_planilhas", str(arquivo), stdout=io.StringIO(), stderr=io.StringIO())
        self.assertEqual(Associado.objects.count(), 0)

    def test_importar_simulacao_nao_grava(self):
        call_command("importar_planilhas", str(RAIZ / "docs" / "exemplo_associados.csv"), "--simular", stdout=io.StringIO())
        self.assertEqual(Associado.objects.count(), 0)

    def test_exportar_dados(self):
        ana = fabrica.associado("Ana")
        Cobranca.objects.create(associado=ana, tipo="MENSALIDADE", competencia=date(2026, 6, 1), valor=Decimal("40"))
        call_command("exportar_dados", "--destino", str(self.pasta), stdout=io.StringIO())
        nomes = sorted(p.name for p in self.pasta.iterdir())
        self.assertEqual(nomes, ["associados.csv", "cobrancas.csv", "despesas.csv", "fechamentos.csv", "leituras.csv", "pagamentos.csv"])
        with (self.pasta / "cobrancas.csv").open(encoding="utf-8-sig") as f:
            linhas = list(csv.reader(f, delimiter=";"))
        self.assertEqual(linhas[0][:3], ["id", "associado_id", "associado__nome"])
        self.assertEqual(linhas[1][2], "Ana")
        self.assertEqual(linhas[1][6], "40.00")


class LoginEmTodasAsTelasTests(TestCase):
    ROTAS = [
        ("core:painel", []), ("core:configuracoes", []),
        ("associados:lista", []), ("associados:novo", []), ("associados:detalhe", [1]), ("associados:editar", [1]),
        ("energia:passo1", []), ("energia:passo2", []), ("energia:passo3", []), ("energia:concluido", []),
        ("cobrancas:lista", []), ("despesas:lista", []), ("despesas:nova", []), ("despesas:editar", [1]),
        ("relatorios:financeiro", []),
    ]
    ROTAS_POST = [
        ("associados:inativar", [1]), ("associados:reativar", [1]), ("energia:cancelar", []),
        ("cobrancas:pagar", [1]), ("cobrancas:lote", []), ("cobrancas:gerar_mensais", []),
        ("despesas:excluir", [1]),
    ]

    def test_sem_sessao_tudo_redireciona_para_login(self):
        for nome, args in self.ROTAS:
            resp = self.client.get(reverse(nome, args=args))
            self.assertEqual(resp.status_code, 302, nome)
            self.assertTrue(resp.url.startswith(reverse("login")), nome)
        for nome, args in self.ROTAS_POST:
            resp = self.client.post(reverse(nome, args=args))
            self.assertEqual(resp.status_code, 302, nome)
            self.assertTrue(resp.url.startswith(reverse("login")), nome)

    def test_build_sh_usa_fim_de_linha_lf(self):
        self.assertNotIn(b"\r\n", (RAIZ / "build.sh").read_bytes())
