"""Regras do fechamento de energia: rateio, disponibilidade, multa e validações.

Todos os cálculos usam Decimal. O fechamento grava leituras e cobranças em uma
única transação: ou grava tudo, ou não grava nada.
"""
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction

from associados.services import elegiveis_energia
from cobrancas.models import Cobranca, RedeCobranca, TipoCobranca
from core.models import Configuracao
from core.utils import arredondar, mes_label, somar_meses

from .models import FechamentoEnergia, Leitura, Rede

SEIS_CASAS = Decimal("0.000001")
ZERO = Decimal("0.00")


class FechamentoInvalido(Exception):
    def __init__(self, erros):
        self.erros = list(erros)
        super().__init__("; ".join(self.erros))


@dataclass
class LinhaRateio:
    associado: object
    leitura_anterior: int
    leitura_atual: int | None
    consumo: int = 0
    valor_energia: Decimal = ZERO
    disponibilidade: Decimal = ZERO
    multa: Decimal = ZERO
    erro: str = ""
    aviso: str = ""

    @property
    def total(self):
        """Valor da cobrança de energia: energia mais taxa de disponibilidade."""
        return self.valor_energia + self.disponibilidade


@dataclass
class Rateio:
    rede: str
    competencia: date
    valor_total: Decimal
    kwh_total: int
    fator: Decimal
    linhas: list = field(default_factory=list)
    erros: list = field(default_factory=list)
    avisos: list = field(default_factory=list)

    @property
    def soma_consumo(self):
        return sum(linha.consumo for linha in self.linhas)

    @property
    def perda_kwh(self):
        return self.kwh_total - self.soma_consumo

    @property
    def perda_valor(self):
        return arredondar(Decimal(self.perda_kwh) * self.fator)

    @property
    def soma_energia(self):
        return sum((linha.valor_energia for linha in self.linhas), ZERO)

    @property
    def soma_disponibilidade(self):
        return sum((linha.disponibilidade for linha in self.linhas), ZERO)

    @property
    def soma_multas(self):
        return sum((linha.multa for linha in self.linhas), ZERO)

    @property
    def soma_cobrancas(self):
        return self.soma_energia + self.soma_disponibilidade

    @property
    def pode_confirmar(self):
        return not self.erros


def calcular_fator(valor_total, kwh_total):
    """fator = valor_total / kwh_total, com 6 casas, meio para cima."""
    return (Decimal(valor_total) / Decimal(kwh_total)).quantize(SEIS_CASAS, rounding=ROUND_HALF_UP)


def vencimento_padrao(competencia):
    """Dia 10 do mês seguinte à competência, como no protótipo."""
    return somar_meses(competencia, 1).replace(day=10)


def ja_fechado(rede, competencia):
    return FechamentoEnergia.objects.filter(rede=rede, competencia=competencia).exists()


def leitura_anterior(associado, rede):
    """Última leitura do associado na rede; no primeiro mês, a leitura inicial do cadastro."""
    ultima = (
        Leitura.objects.filter(associado=associado, fechamento__rede=rede)
        .order_by("-fechamento__competencia")
        .values_list("leitura_atual", flat=True)
        .first()
    )
    if ultima is not None:
        return ultima
    return associado.leitura_inicial(rede) or 0


def calcular_multa(consumo, valor_energia, config):
    """Consumo estritamente acima do limite gera multa sobre o valor da energia (sem a taxa)."""
    if consumo > config.limite_kwh_multa:
        return arredondar(valor_energia * config.percentual_multa / Decimal("100"))
    return ZERO


def calcular_rateio(rede, competencia, valor_total, kwh_total, leituras, config=None):
    """Monta o rateio e as validações sem gravar nada.

    leituras: dicionário {associado_id: leitura_atual ou None}.
    Erros bloqueiam o fechamento; avisos só pedem "Confirmar mesmo assim".
    """
    config = config or Configuracao.atual()
    valor_total = Decimal(valor_total)
    fator = calcular_fator(valor_total, kwh_total)
    rateio = Rateio(rede, competencia, valor_total, int(kwh_total), fator)

    for associado in elegiveis_energia(rede):
        anterior = leitura_anterior(associado, rede)
        atual = leituras.get(associado.pk)
        linha = LinhaRateio(associado, anterior, atual)
        if atual is None:
            linha.erro = "Leitura atual não preenchida."
        elif atual < anterior:
            linha.erro = "Leitura atual menor que a anterior."
        else:
            linha.consumo = atual - anterior
            linha.valor_energia = arredondar(Decimal(linha.consumo) * fator)
            if not associado.e_associacao:
                linha.disponibilidade = config.taxa_disponibilidade
            linha.multa = calcular_multa(linha.consumo, linha.valor_energia, config)
            if linha.consumo == 0:
                linha.aviso = "Leitura zerada: consumo de 0 kWh."
        rateio.linhas.append(linha)

    sem_leitura = sum(1 for linha in rateio.linhas if linha.leitura_atual is None)
    menores = sum(1 for linha in rateio.linhas if linha.erro.startswith("Leitura atual menor"))
    zeradas = sum(1 for linha in rateio.linhas if linha.aviso)
    if sem_leitura:
        rateio.erros.append(f"{sem_leitura} leitura(s) atual(is) não preenchida(s).")
    if menores:
        rateio.erros.append(f"{menores} leitura(s) atual(is) menor(es) que a anterior.")
    if ja_fechado(rede, competencia):
        rateio.erros.append(
            f"A rede {Rede(rede).label} já foi fechada em {mes_label(competencia)}. Não é possível gerar cobranças duplicadas."
        )
    if zeradas:
        rateio.avisos.append(f"{zeradas} associado(s) com leitura zerada (consumo de 0 kWh). Confirme se está correto.")
    if not rateio.erros and rateio.soma_consumo > rateio.kwh_total:
        rateio.avisos.append(
            f"A soma dos consumos ({rateio.soma_consumo} kWh) passa dos kWh da conta ({rateio.kwh_total} kWh)."
        )
    return rateio


def validar_fechamento(rateio):
    """Retorna (erros, avisos) do rateio."""
    return rateio.erros, rateio.avisos


@dataclass
class ResultadoFechamento:
    fechamento: FechamentoEnergia
    qtd_cobrancas: int
    total_cobrancas: Decimal
    qtd_multas: int
    total_multas: Decimal


@transaction.atomic
def fechar_energia(rede, competencia, valor_total, kwh_total, vencimento, leituras, config=None):
    """Grava fechamento, leituras, cobranças de energia e multas em uma transação."""
    config = config or Configuracao.atual()
    rateio = calcular_rateio(rede, competencia, valor_total, kwh_total, leituras, config)
    if rateio.erros:
        raise FechamentoInvalido(rateio.erros)

    try:
        with transaction.atomic():
            fechamento = FechamentoEnergia.objects.create(
                rede=rede, competencia=competencia, valor_total=rateio.valor_total,
                kwh_total=rateio.kwh_total, fator=rateio.fator, vencimento=vencimento,
                perda_kwh=rateio.perda_kwh, perda_valor=rateio.perda_valor,
            )
    except IntegrityError:
        raise FechamentoInvalido([f"A rede {Rede(rede).label} já foi fechada em {mes_label(competencia)}."])

    qtd = qtd_multas = 0
    total = total_multas = ZERO
    for linha in rateio.linhas:
        Leitura.objects.create(
            fechamento=fechamento, associado=linha.associado,
            leitura_anterior=linha.leitura_anterior, leitura_atual=linha.leitura_atual,
            consumo_kwh=linha.consumo, valor_energia=linha.valor_energia,
        )
        # Como no protótipo, não se cria cobrança de valor zero (ex.: Associação sem consumo).
        if linha.total > 0:
            Cobranca.objects.create(
                associado=linha.associado, tipo=TipoCobranca.ENERGIA, rede=RedeCobranca(rede),
                competencia=competencia, valor=linha.total, valor_disponibilidade=linha.disponibilidade,
                vencimento=vencimento, fechamento=fechamento, consumo_kwh=linha.consumo,
            )
            qtd += 1
            total += linha.total
        if linha.multa > 0:
            Cobranca.objects.create(
                associado=linha.associado, tipo=TipoCobranca.MULTA, rede=RedeCobranca(rede),
                competencia=competencia, valor=linha.multa, vencimento=vencimento,
                fechamento=fechamento, consumo_kwh=linha.consumo,
            )
            qtd_multas += 1
            total_multas += linha.multa
    return ResultadoFechamento(fechamento, qtd, total, qtd_multas, total_multas)
