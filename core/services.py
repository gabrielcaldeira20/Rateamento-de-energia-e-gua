"""Números do painel inicial."""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import F

from associados.models import Associado
from cobrancas.models import Cobranca, Pagamento, StatusCobranca
from despesas.models import Despesa

from .utils import hoje, mes_atual, somar


@dataclass
class NumerosPainel:
    competencia: object
    a_receber: Decimal
    entradas: Decimal
    despesas: Decimal
    saldo: Decimal
    associados_ativos: int
    cobrancas_pendentes: int
    em_atraso: Decimal
    qtd_em_atraso: int


def numeros_painel(competencia=None, data_base=None):
    """Painel do mês, por competência, como no protótipo.

    - A receber: saldo das cobranças em aberto com competência no mês.
    - Saldo do mês: pagamentos de cobranças do mês (por competência) menos despesas do mês.
    - Em atraso: saldo das cobranças com vencimento já passado (mensalidade e água não têm vencimento).
    """
    competencia = competencia or mes_atual()
    data_base = data_base or hoje()
    abertas_mes = Cobranca.objects.filter(competencia=competencia).exclude(status=StatusCobranca.PAGA)
    entradas = somar(Pagamento.objects.filter(cobranca__competencia=competencia), "valor")
    despesas = somar(Despesa.objects.filter(competencia=competencia), "valor")
    atrasadas = Cobranca.objects.filter(vencimento__isnull=False, vencimento__lt=data_base).exclude(
        status=StatusCobranca.PAGA
    )
    return NumerosPainel(
        competencia=competencia,
        a_receber=somar(abertas_mes, F("valor") - F("valor_pago")),
        entradas=entradas,
        despesas=despesas,
        saldo=entradas - despesas,
        associados_ativos=Associado.objects.filter(ativo=True).count(),
        cobrancas_pendentes=abertas_mes.count(),
        em_atraso=somar(atrasadas, F("valor") - F("valor_pago")),
        qtd_em_atraso=atrasadas.count(),
    )
