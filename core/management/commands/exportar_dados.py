"""Exporta os dados da associação em CSV (cláusula de entrega em até 15 dias no cancelamento).

Uso: python manage.py exportar_dados [--destino pasta]
Gera um CSV por tabela, separado por ponto e vírgula e em UTF-8 com BOM, que abre direto no Excel.
"""
import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from associados.models import Associado
from cobrancas.models import Cobranca, Pagamento
from core.utils import hoje
from despesas.models import Despesa
from energia.models import FechamentoEnergia, Leitura

TABELAS = {
    "associados": (Associado.objects.order_by("pk"), [
        "id", "nome", "contato", "endereco", "ativo", "e_associacao", "valor_mensalidade",
        "rede_sede", "padrao_ligado_sede", "leitura_inicial_sede",
        "rede_poco", "padrao_ligado_poco", "leitura_inicial_poco", "agua_ligada",
    ]),
    "cobrancas": (Cobranca.objects.order_by("pk"), [
        "id", "associado_id", "associado__nome", "tipo", "rede", "competencia", "valor",
        "valor_disponibilidade", "valor_pago", "vencimento", "status", "fechamento_id", "consumo_kwh",
    ]),
    "pagamentos": (Pagamento.objects.order_by("pk"), [
        "id", "cobranca_id", "cobranca__associado__nome", "valor", "data", "observacao", "lote",
    ]),
    "despesas": (Despesa.objects.order_by("pk"), [
        "id", "descricao", "categoria", "categoria_outra", "valor", "data", "competencia",
    ]),
    "fechamentos": (FechamentoEnergia.objects.order_by("pk"), [
        "id", "rede", "competencia", "valor_total", "kwh_total", "fator", "vencimento", "perda_kwh", "perda_valor",
    ]),
    "leituras": (Leitura.objects.order_by("pk"), [
        "id", "fechamento_id", "associado_id", "associado__nome", "leitura_anterior", "leitura_atual",
        "consumo_kwh", "valor_energia",
    ]),
}


def formatar(valor):
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "sim" if valor else "não"
    return str(valor)


class Command(BaseCommand):
    help = "Exporta associados, cobranças, pagamentos, despesas, fechamentos e leituras em CSV."

    def add_arguments(self, parser):
        parser.add_argument("--destino", help="Pasta de saída (padrão: exportacao-AAAA-MM-DD).")

    def handle(self, *args, **opcoes):
        destino = Path(opcoes.get("destino") or f"exportacao-{hoje():%Y-%m-%d}")
        destino.mkdir(parents=True, exist_ok=True)
        for nome, (qs, campos) in TABELAS.items():
            caminho = destino / f"{nome}.csv"
            with caminho.open("w", newline="", encoding="utf-8-sig") as arquivo:
                escritor = csv.writer(arquivo, delimiter=";")
                escritor.writerow(campos)
                linhas = 0
                for registro in qs.values_list(*campos):
                    escritor.writerow([formatar(v) for v in registro])
                    linhas += 1
            self.stdout.write(f"{caminho}: {linhas} linha(s)")
        self.stdout.write(self.style.SUCCESS(f"Exportação concluída em {destino.resolve()}"))
