"""Relatório financeiro: resumo do período, série mensal e detalhamento.

Modos:
- "pagamento": entradas pelo mês em que o pagamento caiu; despesas pela data.
- "competencia": entradas pelo mês da cobrança paga; despesas pela competência.
A taxa de disponibilidade é a soma do campo valor_disponibilidade das cobranças
de energia com competência no período, nos dois modos.
"""
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from cobrancas.models import Cobranca, Pagamento, TipoCobranca
from core.utils import mes_atual, mes_label, meses_entre, primeiro_dia, somar_meses, ultimo_dia
from despesas.models import Despesa

ZERO = Decimal("0.00")
MODOS = [("pagamento", "Por data de pagamento"), ("competencia", "Por mês de competência")]
PERIODOS = [("atual", "Mês atual"), ("3m", "Últimos 3 meses"), ("6m", "Últimos 6 meses"), ("custom", "Personalizado")]


def resolver_periodo(preset, inicio=None, fim=None, base=None):
    """Retorna (primeiro mês, último mês), sempre no 1º dia de cada mês."""
    base = base or mes_atual()
    if preset == "atual":
        return base, base
    if preset == "3m":
        return somar_meses(base, -2), base
    if preset == "custom" and inicio and fim:
        inicio, fim = primeiro_dia(inicio), primeiro_dia(fim)
        return (inicio, fim) if inicio <= fim else (fim, inicio)
    return somar_meses(base, -5), base


def pagamentos_do_periodo(inicio, fim, modo):
    qs = Pagamento.objects.select_related("cobranca__associado")
    if modo == "competencia":
        return qs.filter(cobranca__competencia__gte=inicio, cobranca__competencia__lte=fim)
    return qs.filter(data__gte=inicio, data__lte=ultimo_dia(fim))


def despesas_do_periodo(inicio, fim, modo):
    if modo == "competencia":
        return Despesa.objects.filter(competencia__gte=inicio, competencia__lte=fim)
    return Despesa.objects.filter(data__gte=inicio, data__lte=ultimo_dia(fim))


def disponibilidade_do_periodo(inicio, fim):
    return Cobranca.objects.select_related("associado").filter(
        tipo=TipoCobranca.ENERGIA, competencia__gte=inicio, competencia__lte=fim, valor_disponibilidade__gt=0,
    )


def _soma(qs, campo):
    return qs.aggregate(s=Sum(campo))["s"] or ZERO


@dataclass
class Resumo:
    entradas: Decimal
    despesas: Decimal
    saldo: Decimal
    disponibilidade: Decimal


def resumo_periodo(inicio, fim, modo="pagamento"):
    entradas = _soma(pagamentos_do_periodo(inicio, fim, modo), "valor")
    despesas = _soma(despesas_do_periodo(inicio, fim, modo), "valor")
    disponibilidade = _soma(disponibilidade_do_periodo(inicio, fim), "valor_disponibilidade")
    return Resumo(entradas, despesas, entradas - despesas, disponibilidade)


def serie_mensal(inicio, fim, modo="pagamento"):
    """Entradas e despesas de cada mês do período, para o gráfico de barras."""
    entradas, despesas = defaultdict(lambda: ZERO), defaultdict(lambda: ZERO)
    for p in pagamentos_do_periodo(inicio, fim, modo):
        mes = p.cobranca.competencia if modo == "competencia" else primeiro_dia(p.data)
        entradas[mes] += p.valor
    for d in despesas_do_periodo(inicio, fim, modo):
        mes = d.competencia if modo == "competencia" else primeiro_dia(d.data)
        despesas[mes] += d.valor
    return [
        {"mes": mes_label(m), "entradas": entradas[m], "despesas": despesas[m]}
        for m in meses_entre(inicio, fim)
    ]
