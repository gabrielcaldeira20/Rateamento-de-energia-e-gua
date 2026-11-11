"""Testes do comando importar_associados."""
import tempfile
from datetime import date
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from associados.models import Associado, HistoricoLigacao
from core import fabrica
from energia import services as energia

CABECALHO = (
    "nome,cpf_cnpj,endereco,telefone,numero_padrao,sede,poco,padrao_ligado,agua,valor_agua,mensalidade,"
    "leitura_sede,leitura_poco,isento_disponibilidade,ativo,observacao"
)
DATA = "2026-12-01"
INICIO = date(2026, 12, 1)
# CPF e CNPJ com dígitos verificadores válidos.
CPF_OK = "529.982.247-25"
CNPJ_OK = "11.222.333/0001-81"


def linha(nome="Joao", cpf=CPF_OK, telefone="38999990001", agua="sim", valor_agua="35", mensalidade="15",
          sede="", poco="", leitura_sede="", leitura_poco="", isento="nao", ativo="sim", observacao="",
          endereco="Mangaba", padrao="", padrao_ligado=None):
    if padrao_ligado is None:
        padrao_ligado = "sim" if (sede in ("sim", "S") or poco in ("sim", "TRUE")) else ""
    return ",".join([nome, cpf, endereco, telefone, padrao, sede, poco, padrao_ligado, agua, valor_agua,
                     mensalidade, leitura_sede, leitura_poco, isento, ativo, observacao])


class ImportarAssociadosTests(TestCase):
    def importar(self, *linhas, separador=",", data=DATA, simular=False):
        texto = "\n".join([CABECALHO, *linhas])
        if separador != ",":
            texto = texto.replace(",", separador)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "associados.csv"
            caminho.write_text(texto, encoding="utf-8-sig")
            saida = StringIO()
            args = [str(caminho)] + ([f"--data-inicio={data}"] if data else []) + (["--simular"] if simular else [])
            try:
                call_command("importar_associados", *args, stdout=saida)
            except CommandError as erro:
                erro.saida = saida.getvalue()
                raise
            return saida.getvalue()

    # ------------------------------------------------------------ colunas de rede vazias

    def test_redes_vazias_nao_inventam_nada(self):
        saida = self.importar(linha(), linha("Ana", cpf="", agua="nao", valor_agua="0"))
        joao = Associado.objects.get(nome="Joao")
        self.assertEqual(joao.cpf_cnpj, CPF_OK)
        self.assertEqual(joao.valor_mensalidade, Decimal("15"))
        self.assertFalse(joao.rede_sede or joao.rede_poco or joao.padrao_ligado_sede or joao.padrao_ligado_poco)
        self.assertIsNone(joao.leitura_inicial_sede)
        self.assertFalse(HistoricoLigacao.objects.filter(tipo__in=["SEDE", "POCO"]).exists())
        self.assertIn("Sem rede: 2", saida)
        self.assertIn("Com leitura inicial: 0", saida)
        self.assertIn("Sem CPF/CNPJ: 1", saida)

    def test_associado_sem_rede_nenhuma_nao_e_erro(self):
        self.importar(linha(sede="nao", poco="nao"))
        self.assertTrue(Associado.objects.filter(nome="Joao").exists())

    def test_redes_informadas_criam_historico_e_leitura(self):
        self.importar(linha(sede="sim", poco="nao", leitura_sede="1520"),
                      linha("Ana", cpf=CNPJ_OK, sede="S", poco="TRUE", leitura_sede="10", leitura_poco="0"))
        joao = Associado.objects.get(nome="Joao")
        self.assertTrue(joao.rede_sede and joao.padrao_ligado_sede)
        self.assertEqual(joao.leitura_inicial_sede, 1520)
        self.assertEqual(
            list(HistoricoLigacao.objects.filter(associado=joao, tipo__in=["SEDE", "POCO"]).values_list("tipo", "data")),
            [("SEDE", INICIO)],
        )
        ana = Associado.objects.get(nome="Ana")
        self.assertEqual(ana.leitura_inicial_poco, 0)  # zero é leitura válida
        self.assertEqual(energia.leitura_anterior(ana, "POCO"), 0)

    def test_segunda_rodada_preenche_redes_sem_duplicar(self):
        self.importar(linha(), linha("Ana", cpf=""))
        saida = self.importar(linha(sede="sim", leitura_sede="100"), linha("Ana", cpf="", poco="sim", leitura_poco="7"))
        self.assertIn("criados: 0", saida)
        self.assertIn("atualizados: 2", saida)
        self.assertEqual(Associado.objects.count(), 2)
        self.assertTrue(Associado.objects.get(nome="Joao").rede_sede)
        self.assertEqual(Associado.objects.get(nome="Ana").leitura_inicial_poco, 7)

    # ------------------------------------------------------------ água

    def test_agua_cria_um_historico_so(self):
        self.importar(linha(), linha("Ana", cpf="", agua="nao", valor_agua="0"))
        joao = Associado.objects.get(nome="Joao")
        self.assertTrue(joao.agua_ligada)
        registro = HistoricoLigacao.objects.get(associado=joao, tipo="AGUA")
        self.assertEqual((registro.ligado, registro.data), (True, INICIO))
        self.assertFalse(HistoricoLigacao.objects.filter(associado__nome="Ana").exists())

        self.importar(linha(), linha("Ana", cpf="", agua="nao", valor_agua="0"))
        self.assertEqual(HistoricoLigacao.objects.filter(associado=joao, tipo="AGUA").count(), 1)

    def test_agua_ja_com_historico_nao_ganha_outro(self):
        existente = fabrica.associado("Joao", sede=False, agua_ligada=True, cpf_cnpj=CPF_OK, ligado_desde=date(2025, 1, 1))
        self.importar(linha())
        self.assertEqual(HistoricoLigacao.objects.filter(associado=existente, tipo="AGUA").count(), 1)

    def test_avisa_valor_agua_diferente(self):
        saida = self.importar(linha(valor_agua="25"))
        self.assertIn("valor_agua R$ 25 difere do valor único da Configuração", saida)
        self.assertIn("Linha 2 (Joao)", saida)

    # ------------------------------------------------------------ documento e telefone

    def test_sem_documento_grava_nulo_e_nao_colide(self):
        self.importar(linha("Ana", cpf=""), linha("Bia", cpf=""), linha("Caio", cpf="", telefone=""))
        self.assertEqual(Associado.objects.filter(cpf_cnpj__isnull=True).count(), 3)
        self.assertFalse(Associado.objects.filter(cpf_cnpj="").exists())
        self.assertEqual(Associado.objects.get(nome="Caio").contato, "")

    def test_digito_verificador_invalido_so_avisa(self):
        saida = self.importar(linha(cpf="111.222.333-44"), linha("Clube", cpf="07.848.669/0001-00"))
        self.assertEqual(Associado.objects.count(), 2)
        self.assertIn("CPF 111.222.333-44 com dígito verificador inválido", saida)
        self.assertIn("CNPJ 07.848.669/0001-00 com dígito verificador inválido", saida)

    def test_cnpj_cabe_no_campo(self):
        self.importar(linha("Clube", cpf=CNPJ_OK))
        self.assertEqual(Associado.objects.get(nome="Clube").cpf_cnpj, CNPJ_OK)

    def test_procura_por_documento_antes_do_nome(self):
        self.importar(linha("Joao"))
        saida = self.importar(linha("João da Silva"))  # mesmo CPF, nome corrigido
        self.assertIn("atualizados: 1", saida)
        self.assertEqual(Associado.objects.get().nome, "João da Silva")

    def test_homonimos_com_documentos_diferentes(self):
        self.importar(linha("Bartolomeu"), linha("Bartolomeu", cpf=CNPJ_OK))
        self.assertEqual(Associado.objects.filter(nome="Bartolomeu").count(), 2)

    def test_documento_novo_para_nome_ja_cadastrado_sem_documento_para(self):
        self.importar(linha("Ana", cpf=""))
        with self.assertRaises(CommandError) as ctx:
            self.importar(linha("Ana", cpf=CPF_OK))
        self.assertIn("já existe associado com este nome e sem CPF/CNPJ", ctx.exception.saida)
        self.assertEqual(Associado.objects.count(), 1)

    def test_telefone_vazio_nao_apaga_o_existente(self):
        self.importar(linha())
        self.importar(linha(telefone=""))
        self.assertEqual(Associado.objects.get().contato, "38999990001")

    # ------------------------------------------------------------ execução

    def test_ponto_e_virgula(self):
        self.importar(linha(), separador=";")
        self.assertTrue(Associado.objects.filter(nome="Joao").exists())

    def test_simular_nao_grava(self):
        saida = self.importar(linha(), simular=True)
        self.assertIn("seriam criados: 1", saida)
        self.assertFalse(Associado.objects.exists())
        self.assertFalse(HistoricoLigacao.objects.exists())

    def test_data_inicio_obrigatoria_e_no_dia_1(self):
        with self.assertRaisesMessage(CommandError, "--data-inicio"):
            self.importar(linha(), data=None)
        with self.assertRaisesMessage(CommandError, "primeiro dia do mês"):
            self.importar(linha(), data="2026-12-15")

    def test_uma_linha_com_erro_nada_e_gravado(self):
        casos = [
            linha("", cpf=CNPJ_OK),                                  # nome vazio
            linha("Ana", cpf=CNPJ_OK, sede="sim", leitura_sede="5", padrao_ligado=""),  # sem padrao_ligado
            linha("Ana", cpf=CNPJ_OK, padrao="7"),                    # padrão repetido
            linha("Ana", cpf=CNPJ_OK, sede="nao", leitura_sede="5"),  # leitura em rede desligada
            linha("Ana", cpf=CNPJ_OK, leitura_sede="5"),              # leitura com rede vazia
            linha("Ana", cpf=CNPJ_OK, sede="sim", leitura_sede="-5"),
            linha("Ana", cpf=CNPJ_OK, sede="sim", leitura_sede="1,5"),
            linha("Ana", cpf=CNPJ_OK, agua="talvez"),
            linha("Ana", cpf=CNPJ_OK, valor_agua="-1"),
            linha("Ana", cpf=CNPJ_OK, mensalidade="-15"),
            linha("Ana", cpf=CPF_OK),                                # CPF repetido na planilha
            linha("Ana", cpf=CNPJ_OK, padrao="abc"),
        ]
        for caso in casos:
            with self.subTest(caso=caso), self.assertRaises(CommandError) as ctx:
                self.importar(linha(padrao="7"), caso)
            self.assertIn("Linha 3", ctx.exception.saida)
            self.assertIn("Linhas rejeitadas: 1", ctx.exception.saida)
            self.assertFalse(Associado.objects.exists())

    def test_avisa_observacao_e_isencao_ignoradas(self):
        saida = self.importar(linha(observacao="medidor trocado", isento="sim"))
        self.assertIn("observação descartada", saida)
        self.assertIn("isento_disponibilidade = sim não é importado", saida)
        self.assertFalse(Associado.objects.get().e_associacao)

    # ------------------------------------------------------------ numero_padrao e rede sem leitura

    def test_rede_sem_leitura_nao_liga_e_so_avisa(self):
        saida = self.importar(
            linha(padrao="5", sede="sim", poco="nao", padrao_ligado="sim"),
            linha("Ana", cpf=CNPJ_OK, padrao="16", sede="sim", poco="nao", padrao_ligado="nao"),
            linha("Bia", cpf="", padrao="27", sede="nao", poco="sim", padrao_ligado="nao"),
        )
        self.assertEqual(Associado.objects.count(), 3)
        for a in Associado.objects.all():
            self.assertFalse(a.rede_sede or a.rede_poco or a.padrao_ligado_sede or a.padrao_ligado_poco)
        self.assertFalse(HistoricoLigacao.objects.filter(tipo__in=["SEDE", "POCO"]).exists())
        self.assertEqual(Associado.objects.get(nome="Joao").numero_padrao, 5)
        self.assertIn("Com rede definida: 3 (Sede: 2, Poço: 1)", saida)
        self.assertIn("Padrão desligado: 2", saida)
        self.assertIn("Rede informada sem leitura inicial: 3", saida)
        self.assertIn("Linha 3 (Ana): rede Sede informada sem leitura_sede: não ligada nesta importação (padrão desligado)", saida)

    def test_sem_padrao_grava_nulo(self):
        self.importar(linha(), linha("Ana", cpf=CNPJ_OK))
        self.assertEqual(Associado.objects.filter(numero_padrao__isnull=True).count(), 2)

    def test_casa_pelo_numero_padrao_quando_nao_ha_documento(self):
        self.importar(linha("Marcio", cpf="", padrao="38", sede="sim"))
        saida = self.importar(linha("Márcio Barbosa", cpf="", padrao="38", sede="sim", leitura_sede="900"))
        self.assertIn("atualizados: 1", saida)
        marcio = Associado.objects.get()
        self.assertEqual(marcio.nome, "Márcio Barbosa")
        self.assertTrue(marcio.rede_sede and marcio.padrao_ligado_sede)
        self.assertEqual(marcio.leitura_inicial_sede, 900)
        self.assertTrue(HistoricoLigacao.objects.filter(associado=marcio, tipo="SEDE", data=INICIO, ligado=True).exists())

    def test_segunda_rodada_com_leitura_e_padrao_desligado(self):
        self.importar(linha(padrao="16", sede="sim", poco="nao", padrao_ligado="nao"))
        self.importar(linha(padrao="16", sede="sim", poco="nao", padrao_ligado="nao", leitura_sede="300"))
        joao = Associado.objects.get()
        self.assertTrue(joao.rede_sede)
        self.assertFalse(joao.padrao_ligado_sede)
        self.assertNotIn(joao, energia.elegiveis_energia("SEDE"))

    def test_coluna_energia_antiga_e_ignorada(self):
        global CABECALHO
        original = CABECALHO
        try:
            CABECALHO = original + ",energia"
            saida = self.importar(linha() + ",sim")
        finally:
            CABECALHO = original
        self.assertIn("Coluna energia ignorada", saida)
