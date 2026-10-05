"""Testes do histórico de ligações."""
from datetime import date, datetime
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from associados import services
from associados.forms import AssociadoForm
from associados.models import Associado, HistoricoLigacao
from cobrancas import services as cobrancas
from cobrancas.models import Cobranca
from core import fabrica
from energia import services as energia

JUN, JUL = date(2026, 6, 1), date(2026, 7, 1)


class SituacaoEmTests(TestCase):
    def setUp(self):
        self.a = fabrica.associado("Ana", ligado_desde=None)
        for data, ligado in ((date(2026, 3, 15), True), (date(2026, 6, 10), False), (date(2026, 8, 1), True)):
            HistoricoLigacao.objects.create(associado=self.a, tipo="SEDE", ligado=ligado, data=data)

    def test_varias_datas(self):
        casos = {
            date(2026, 3, 14): False,  # antes do primeiro registro
            date(2026, 3, 15): True,   # no mesmo dia da mudança, vale o novo estado
            date(2026, 6, 9): True,
            date(2026, 6, 10): False,
            date(2026, 7, 31): False,
            date(2026, 8, 1): True,
            date(2030, 1, 1): True,
        }
        for data, esperado in casos.items():
            self.assertEqual(services.situacao_em(self.a, "SEDE", data), esperado, data)

    def test_sem_registro_e_desligado(self):
        self.assertFalse(services.situacao_em(self.a, "POCO", date(2026, 9, 1)))
        self.assertFalse(services.situacao_em(self.a, "AGUA", date(2026, 9, 1)))

    def test_competencia_vale_o_ultimo_dia_do_mes(self):
        self.assertTrue(services.situacao_na_competencia(self.a, "SEDE", date(2026, 3, 1)))
        self.assertFalse(services.situacao_na_competencia(self.a, "SEDE", JUN))
        self.assertFalse(services.situacao_na_competencia(self.a, "SEDE", JUL))
        self.assertTrue(services.situacao_na_competencia(self.a, "SEDE", date(2026, 8, 1)))


class EstadoAtualTests(TestCase):
    def setUp(self):
        self.a = fabrica.associado("Ana", ligado_desde=date(2025, 1, 1))

    def test_registro_retroativo_atualiza_estado_atual(self):
        # Registro anterior ao mais recente não muda o estado atual.
        services.salvar_registro(self.a, "SEDE", False, date(2024, 12, 1))
        self.a.refresh_from_db()
        self.assertTrue(self.a.rede_sede)
        # Desligamento retroativo mais recente que tudo: passa a valer.
        registro = services.salvar_registro(self.a, "SEDE", False, date(2025, 9, 1), "Corte")
        self.a.refresh_from_db()
        self.assertFalse(self.a.rede_sede)
        self.assertFalse(self.a.padrao_ligado_sede)
        # Editar a data para antes da ligação devolve o estado ligado.
        services.salvar_registro(self.a, "SEDE", False, date(2024, 6, 1), registro=registro)
        self.a.refresh_from_db()
        self.assertTrue(self.a.rede_sede)
        # Excluir o registro de ligação deixa o desligamento como mais recente.
        services.excluir_registro(HistoricoLigacao.objects.get(associado=self.a, tipo="SEDE", data=date(2025, 1, 1)))
        self.a.refresh_from_db()
        self.assertFalse(self.a.rede_sede)

    def test_estado_atual_e_por_data_e_nao_por_ordem_de_criacao(self):
        services.salvar_registro(self.a, "AGUA", True, date(2025, 8, 1))
        services.salvar_registro(self.a, "AGUA", False, date(2025, 3, 1))  # criado depois, data mais antiga
        self.a.refresh_from_db()
        self.assertTrue(self.a.agua_ligada)

    def test_duas_mudancas_na_mesma_data_nao_duplicam(self):
        services.salvar_registro(self.a, "AGUA", True, date(2025, 5, 5), "Ligada")
        services.salvar_registro(self.a, "AGUA", False, date(2025, 5, 5), "Engano, desligada")
        registros = HistoricoLigacao.objects.filter(associado=self.a, tipo="AGUA")
        self.assertEqual(registros.count(), 1)
        self.assertFalse(registros.get().ligado)
        self.a.refresh_from_db()
        self.assertFalse(self.a.agua_ligada)

    def test_editar_para_data_ocupada_e_recusado(self):
        r = services.salvar_registro(self.a, "SEDE", False, date(2025, 9, 1))
        with self.assertRaises(services.ErroHistorico):
            services.salvar_registro(self.a, "SEDE", True, date(2025, 1, 1), registro=r)

    def test_ligar_rede_continua_exigindo_leitura_inicial(self):
        sem_poco = self.a
        with self.assertRaises(services.ErroHistorico):
            services.salvar_registro(sem_poco, "POCO", True, date(2025, 2, 1))
        self.assertFalse(HistoricoLigacao.objects.filter(associado=sem_poco, tipo="POCO").exists())
        services.salvar_registro(sem_poco, "POCO", True, date(2025, 2, 1), leitura_inicial=300)
        sem_poco.refresh_from_db()
        self.assertTrue(sem_poco.rede_poco)
        self.assertEqual(sem_poco.leitura_inicial_poco, 300)


class FormularioAssociadoTests(TestCase):
    def dados(self, **extra):
        base = {"nome": "Bia", "contato": "(38) 98888-1111", "valor_mensalidade": "40.00"}
        base.update(extra)
        return base

    def test_cadastro_grava_ligado_desde(self):
        form = AssociadoForm(data=self.dados(rede_sede="on", padrao_ligado_sede="on", leitura_inicial_sede="10",
                                             agua_ligada="on", data_mudanca="2025-04-01"))
        self.assertTrue(form.is_valid(), form.errors)
        a = form.save()
        registros = {(r.tipo, r.ligado, r.data) for r in a.historico_ligacoes.all()}
        self.assertEqual(registros, {("SEDE", True, date(2025, 4, 1)), ("AGUA", True, date(2025, 4, 1))})

    def test_data_padrao_e_hoje_e_futuro_e_recusado(self):
        form = AssociadoForm(data=self.dados(agua_ligada="on"))
        self.assertTrue(form.is_valid(), form.errors)
        a = form.save()
        self.assertEqual(a.historico_ligacoes.get().data, timezone.localdate())
        futuro = AssociadoForm(data=self.dados(nome="X", data_mudanca="2999-01-01"))
        self.assertFalse(futuro.is_valid())
        self.assertIn("data_mudanca", futuro.errors)

    def test_edicao_grava_so_o_que_mudou(self):
        a = AssociadoForm(data=self.dados(agua_ligada="on", data_mudanca="2025-01-01"))
        a.is_valid()
        a = a.save()
        form = AssociadoForm(data=self.dados(data_mudanca="2025-06-15"), instance=a)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        a.refresh_from_db()
        self.assertFalse(a.agua_ligada)
        self.assertEqual(
            list(a.historico_ligacoes.order_by("data").values_list("tipo", "ligado", "data")),
            [("AGUA", True, date(2025, 1, 1)), ("AGUA", False, date(2025, 6, 15))],
        )

    def test_regra_da_leitura_inicial_continua(self):
        form = AssociadoForm(data=self.dados(rede_poco="on"))
        self.assertFalse(form.is_valid())
        self.assertIn("leitura_inicial_poco", form.errors)


class UsoNoRateioENaGeracaoTests(TestCase):
    def setUp(self):
        self.antigo = fabrica.associado("Antigo", ligado_desde=date(2025, 1, 1))
        self.novo = fabrica.associado("Novo", ligado_desde=date(2026, 7, 1))
        self.saiu = fabrica.associado("Saiu", ligado_desde=date(2025, 1, 1))
        services.salvar_registro(self.saiu, "SEDE", False, date(2026, 8, 1))

    def test_rateio_de_competencia_antiga_exclui_quem_ainda_nao_estava_ligado(self):
        rateio = energia.calcular_rateio("SEDE", JUN, Decimal("100"), 200, {})
        nomes = [l.associado.nome for l in rateio.linhas]
        self.assertEqual(nomes, ["Antigo", "Saiu"])  # quem desligou depois entra em junho
        rateio = energia.calcular_rateio("SEDE", JUL, Decimal("100"), 200, {})
        self.assertEqual([l.associado.nome for l in rateio.linhas], ["Antigo", "Novo", "Saiu"])
        rateio = energia.calcular_rateio("SEDE", date(2026, 8, 1), Decimal("100"), 200, {})
        self.assertEqual([l.associado.nome for l in rateio.linhas], ["Antigo", "Novo"])

    def test_tela_de_leituras_usa_o_historico(self):
        self.client.force_login(fabrica.tesoureiro())
        self.client.post(reverse("energia:passo1"), {"rede": "SEDE", "competencia": "2026-06",
                         "vencimento": "2026-07-10", "valor_total": "100", "kwh_total": "200"})
        resp = self.client.get(reverse("energia:passo2"))
        self.assertContains(resp, "Antigo")
        self.assertNotContains(resp, "Novo")

    def test_agua_so_para_quem_a_tinha_ligada_na_competencia(self):
        ligou = fabrica.associado("Ligou", sede=False, ligado_desde=None)
        services.salvar_registro(ligou, "AGUA", True, date(2026, 7, 15))
        desligou = fabrica.associado("Desligou", sede=False, agua_ligada=True, ligado_desde=date(2025, 1, 1))
        services.salvar_registro(desligou, "AGUA", False, date(2026, 6, 10))

        cobrancas.gerar_mensais(JUN)
        aguas_jun = set(Cobranca.objects.filter(tipo="AGUA", competencia=JUN).values_list("associado__nome", flat=True))
        self.assertEqual(aguas_jun, set())
        cobrancas.gerar_mensais(JUL)
        aguas_jul = set(Cobranca.objects.filter(tipo="AGUA", competencia=JUL).values_list("associado__nome", flat=True))
        self.assertEqual(aguas_jul, {"Ligou"})  # vale o estado no último dia do mês
        # Mensalidade continua para todos os ativos.
        self.assertEqual(Cobranca.objects.filter(tipo="MENSALIDADE", competencia=JUN).count(), 5)

    def test_cobrancas_ja_criadas_nao_sao_recalculadas(self):
        energia.fechar_energia("SEDE", JUN, Decimal("100"), 200, date(2026, 7, 10),
                               {self.antigo.pk: 1050, self.saiu.pk: 1050})
        antes = list(Cobranca.objects.values_list("pk", "valor", "valor_disponibilidade"))
        services.salvar_registro(self.antigo, "SEDE", False, date(2025, 6, 1))
        services.excluir_registro(HistoricoLigacao.objects.get(associado=self.saiu, tipo="SEDE", data=date(2025, 1, 1)))
        self.assertEqual(list(Cobranca.objects.values_list("pk", "valor", "valor_disponibilidade")), antes)


class TelasHistoricoTests(TestCase):
    def setUp(self):
        self.client.force_login(fabrica.tesoureiro())
        self.a = fabrica.associado("Ana", ligado_desde=date(2025, 1, 1))

    def test_linha_do_tempo_adicionar_editar_excluir(self):
        url = reverse("associados:historico", args=[self.a.pk])
        self.assertContains(self.client.get(url), "Linha do tempo")
        resp = self.client.post(url, {"tipo": "SEDE", "ligado": "0", "data": "2025-09-01", "observacao": "Corte"})
        self.assertRedirects(resp, url)
        self.a.refresh_from_db()
        self.assertFalse(self.a.rede_sede)
        r = HistoricoLigacao.objects.get(data=date(2025, 9, 1))
        resp = self.client.post(reverse("historico:editar", args=[r.pk]),
                                {"tipo": "SEDE", "ligado": "0", "data": "2024-09-01", "observacao": "Corte antigo"})
        self.assertRedirects(resp, url)
        self.a.refresh_from_db()
        self.assertTrue(self.a.rede_sede)
        self.client.post(reverse("historico:excluir", args=[r.pk]))
        self.assertFalse(HistoricoLigacao.objects.filter(pk=r.pk).exists())

    def test_ligar_rede_sem_leitura_pede_leitura(self):
        url = reverse("associados:historico", args=[self.a.pk])
        resp = self.client.post(url, {"tipo": "POCO", "ligado": "1", "data": "2025-02-01"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "leitura inicial")

    def test_lista_filtravel_e_menu_liberado(self):
        outro = fabrica.associado("Bruno", ligado_desde=date(2026, 2, 1))
        url = reverse("historico:lista")
        resp = self.client.get(url)
        self.assertEqual(len(resp.context["registros"]), 2)
        self.assertEqual(len(self.client.get(url, {"associado": outro.pk}).context["registros"]), 1)
        self.assertEqual(len(self.client.get(url, {"tipo": "AGUA"}).context["registros"]), 0)
        self.assertEqual(len(self.client.get(url, {"de": "2026-01-01", "ate": "2026-12-31"}).context["registros"]), 1)
        self.assertEqual(len(self.client.get(url, {"de": "2026-02-31"}).context["registros"]), 2)  # data inválida é ignorada
        self.assertContains(resp, f'href="{url}"')
        self.assertNotContains(resp, 'title="Disponível no plano Completo"><i class="bi bi-clock-history')

    def test_telas_exigem_login(self):
        r = HistoricoLigacao.objects.first()
        self.client.logout()
        for metodo, url in (("get", reverse("historico:lista")), ("get", reverse("associados:historico", args=[self.a.pk])),
                            ("get", reverse("historico:editar", args=[r.pk])), ("post", reverse("historico:excluir", args=[r.pk]))):
            resp = getattr(self.client, metodo)(url)
            self.assertEqual(resp.status_code, 302, url)
            self.assertTrue(resp.url.startswith(reverse("login")))


class MigracaoTests(TransactionTestCase):
    outros = [("energia", "0001_initial"), ("cobrancas", "0002_initial")]
    antes = [("associados", "0002_historico_ligacao")] + outros
    depois = [("associados", "0003_carga_historico_ligacoes")] + outros

    def migrar(self, alvo):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(alvo)
        return executor.loader.project_state(alvo).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_aplica_e_reverte_em_banco_vazio(self):
        self.migrar(self.antes)
        apps = self.migrar(self.depois)
        self.assertEqual(apps.get_model("associados", "HistoricoLigacao").objects.count(), 0)
        apps = self.migrar(self.antes)
        self.assertEqual(apps.get_model("associados", "HistoricoLigacao").objects.count(), 0)

    def test_carga_com_dados_e_reversao(self):
        apps = self.migrar(self.antes)
        Associado_ = apps.get_model("associados", "Associado")
        Fechamento = apps.get_model("energia", "FechamentoEnergia")
        Leitura = apps.get_model("energia", "Leitura")
        Cobranca_ = apps.get_model("cobrancas", "Cobranca")

        criado = timezone.make_aware(datetime(2026, 9, 20, 10, 0))
        antigo = Associado_.objects.create(nome="Antigo", contato="1", rede_sede=True, padrao_ligado_sede=True,
                                           leitura_inicial_sede=100, agua_ligada=True)
        sem_mov = Associado_.objects.create(nome="Sem movimento", contato="2", rede_poco=True, leitura_inicial_poco=5)
        desligado = Associado_.objects.create(nome="Desligado", contato="3")
        Associado_.objects.update(criado_em=criado)
        f = Fechamento.objects.create(rede="SEDE", competencia=date(2026, 3, 1), valor_total=Decimal("50"), kwh_total=50,
                                      fator=Decimal("1"), vencimento=date(2026, 4, 10), perda_kwh=0, perda_valor=Decimal("0"))
        Leitura.objects.create(fechamento=f, associado=antigo, leitura_anterior=100, leitura_atual=150,
                               consumo_kwh=50, valor_energia=Decimal("50"))
        Cobranca_.objects.create(associado=antigo, tipo="ENERGIA", rede="SEDE", competencia=date(2026, 3, 1),
                                 valor=Decimal("55"), valor_disponibilidade=Decimal("5"), fechamento=f)
        Cobranca_.objects.create(associado=antigo, tipo="MENSALIDADE", rede="NENHUMA", competencia=date(2026, 1, 1),
                                 valor=Decimal("40"))
        fechamentos_antes = list(Fechamento.objects.values())
        cobrancas_antes = list(Cobranca_.objects.order_by("pk").values())

        apps = self.migrar(self.depois)
        Historico = apps.get_model("associados", "HistoricoLigacao")
        registros = {(h.associado.nome, h.tipo, h.ligado, h.data) for h in Historico.objects.select_related("associado")}
        self.assertEqual(registros, {
            ("Antigo", "SEDE", True, date(2026, 1, 1)),   # competência mais antiga (mensalidade de janeiro)
            ("Antigo", "AGUA", True, date(2026, 1, 1)),
            ("Sem movimento", "POCO", True, date(2026, 9, 20)),  # sem leitura nem cobrança: data de criação
        })
        self.assertEqual(list(apps.get_model("energia", "FechamentoEnergia").objects.values()), fechamentos_antes)
        self.assertEqual(list(apps.get_model("cobrancas", "Cobranca").objects.order_by("pk").values()), cobrancas_antes)

        apps = self.migrar(self.antes)
        self.assertEqual(apps.get_model("associados", "HistoricoLigacao").objects.count(), 0)
        self.assertEqual(apps.get_model("associados", "Associado").objects.count(), 3)
        self.assertEqual(list(apps.get_model("cobrancas", "Cobranca").objects.order_by("pk").values()), cobrancas_antes)
