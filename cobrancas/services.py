"""Regras de cobrança: geração mensal, pagamentos, crédito, baixa em lote e WhatsApp."""
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import quote

from django.db import transaction
from django.db.models import F, Sum

from associados.models import Associado
from associados.services import situacoes_na_competencia
from core.models import Configuracao
from core.utils import ZERO, formatar_brl, hoje, mes_label

from .models import Cobranca, MovimentoCredito, Pagamento, RedeCobranca, StatusCobranca, TipoCobranca


class PagamentoInvalido(Exception):
    pass


# ---------------------------------------------------------------- geração mensal

@dataclass
class ResultadoGeracao:
    criadas: int
    existentes: int
    total_criado: Decimal


@transaction.atomic
def gerar_mensais(competencia, config=None):
    """Cria mensalidade e, se a água estava ligada na competência (histórico), água para cada associado ativo.

    Rodar duas vezes não duplica: o que já existe é contado em "existentes".
    Como no protótipo, não se cria cobrança de valor zero.
    """
    config = config or Configuracao.atual()
    criadas = existentes = 0
    total = ZERO
    associados = list(Associado.objects.filter(ativo=True))
    agua_ligada = situacoes_na_competencia(associados, "AGUA", competencia)
    for associado in associados:
        itens = []
        if associado.valor_mensalidade > 0:
            itens.append((TipoCobranca.MENSALIDADE, associado.valor_mensalidade))
        if config.valor_agua > 0 and agua_ligada[associado.pk]:
            itens.append((TipoCobranca.AGUA, config.valor_agua))
        for tipo, valor in itens:
            _, criada = Cobranca.objects.get_or_create(
                associado=associado, tipo=tipo, competencia=competencia, rede=RedeCobranca.NENHUMA,
                defaults={"valor": valor},
            )
            if criada:
                criadas += 1
                total += valor
            else:
                existentes += 1
    return ResultadoGeracao(criadas, existentes, total)


# ---------------------------------------------------------------- pagamentos

@dataclass
class ResultadoPagamento:
    pagamento: Pagamento
    credito_gerado: Decimal


def _registrar(cobranca, valor, data, observacao="", lote=None):
    """Aplica o pagamento a uma cobrança já travada. O excedente vira crédito."""
    valor = Decimal(valor)
    if valor <= 0:
        raise PagamentoInvalido("O valor do pagamento deve ser maior que zero.")
    if cobranca.status == StatusCobranca.PAGA:
        raise PagamentoInvalido("Esta cobrança já está paga.")
    aplicado = min(valor, cobranca.saldo)
    excedente = valor - aplicado
    cobranca.valor_pago = cobranca.valor_pago + aplicado
    cobranca.atualizar_status()
    cobranca.save(update_fields=["valor_pago", "status"])
    pagamento = Pagamento.objects.create(
        cobranca=cobranca, valor=valor, data=data, observacao=observacao, lote=lote,
    )
    if excedente > 0:
        MovimentoCredito.objects.create(
            associado_id=cobranca.associado_id, valor=excedente, pagamento=pagamento, data=data,
        )
    return ResultadoPagamento(pagamento, excedente)


@transaction.atomic
def registrar_pagamento(cobranca_id, valor, data, observacao=""):
    """Pagamento individual: menor que o saldo deixa parcial; maior quita e gera crédito."""
    cobranca = Cobranca.objects.select_for_update().get(pk=cobranca_id)
    return _registrar(cobranca, valor, data, observacao)


@transaction.atomic
def baixar_em_lote(ids, data=None):
    """Paga o saldo restante de cada cobrança marcada, na mesma data e com o mesmo lote.

    Roda em uma transação: se uma falhar, nenhuma é paga.
    Cobranças já pagas são ignoradas. Retorna (quantidade, total, lote).
    """
    data = data or hoje()
    lote = uuid.uuid4()
    qtd, total = 0, ZERO
    for cobranca in Cobranca.objects.select_for_update().filter(pk__in=ids).order_by("pk"):
        if cobranca.status == StatusCobranca.PAGA:
            continue
        saldo = cobranca.saldo
        _registrar(cobranca, saldo, data, "Pago em lote", lote)
        qtd += 1
        total += saldo
    return qtd, total, lote


# ---------------------------------------------------------------- saldos e crédito

def _brutos_e_creditos(ids):
    brutos = defaultdict(lambda: ZERO)
    for linha in (
        Cobranca.objects.filter(associado_id__in=ids).exclude(status=StatusCobranca.PAGA)
        .values("associado_id").annotate(s=Sum(F("valor") - F("valor_pago")))
    ):
        brutos[linha["associado_id"]] = linha["s"] or ZERO
    creditos = defaultdict(lambda: ZERO)
    for linha in MovimentoCredito.objects.filter(associado_id__in=ids).values("associado_id").annotate(s=Sum("valor")):
        creditos[linha["associado_id"]] = linha["s"] or ZERO
    return brutos, creditos


def saldos_devedores(ids):
    """Saldo devedor exibido: saldo em aberto menos o crédito, nunca negativo (como no protótipo).

    O crédito só reduz o número exibido. Ele nunca quita cobranças sozinho.
    """
    brutos, creditos = _brutos_e_creditos(ids)
    return {i: max(ZERO, brutos[i] - creditos[i]) for i in ids}


def credito_disponivel(associado):
    """Crédito que sobra depois de abater o saldo em aberto (como no protótipo)."""
    brutos, creditos = _brutos_e_creditos([associado.pk])
    return max(ZERO, creditos[associado.pk] - brutos[associado.pk])


def resumo_associado(associado):
    saldo = saldos_devedores([associado.pk])[associado.pk]
    return {
        "cobrancas": associado.cobrancas.all(),
        "saldo_devedor": saldo,
        "credito": credito_disponivel(associado),
    }


# ---------------------------------------------------------------- lista

TIPOS_FILTRO = [
    ("ENERGIA:SEDE", "Energia (Sede)"),
    ("ENERGIA:POCO", "Energia (Poço)"),
    ("MULTA", "Multa"),
    ("MENSALIDADE", "Mensalidade"),
    ("AGUA", "Água"),
]


def filtrar(busca="", tipo="todos", competencia=None, status="PENDENTE"):
    qs = Cobranca.objects.select_related("associado")
    if busca:
        qs = qs.filter(associado__nome__icontains=busca)
    if tipo and tipo != "todos":
        if ":" in tipo:
            tipo, rede = tipo.split(":", 1)
            qs = qs.filter(tipo=tipo, rede=rede)
        else:
            qs = qs.filter(tipo=tipo)
    if competencia:
        qs = qs.filter(competencia=competencia)
    if status and status != "todos":
        qs = qs.filter(status=status)
    return qs.order_by("-competencia", "tipo", "associado__nome")


# ---------------------------------------------------------------- WhatsApp

def telefone_whatsapp(contato):
    """Só dígitos, com o prefixo 55 do Brasil. Retorna None se não houver telefone válido.

    Números com 10 ou 11 dígitos (DDD + número) sempre recebem 55, inclusive os do DDD 55.
    """
    digitos = re.sub(r"\D", "", contato or "")
    if len(digitos) < 10:
        return None
    if len(digitos) >= 12 and digitos.startswith("55"):
        return digitos
    return "55" + digitos


def mensagem_whatsapp(cobranca, config=None):
    config = config or Configuracao.atual()
    tipo = cobranca.rotulo_tipo
    tipo = tipo[0].lower() + tipo[1:]
    return (
        f"Olá, {cobranca.associado.nome}! Passando para lembrar da cobrança de {tipo} "
        f"de {mes_label(cobranca.competencia)}, no valor de R$ {formatar_brl(cobranca.saldo, simbolo=False)}. "
        f"Chave PIX: {config.chave_pix}."
    )


def link_whatsapp(cobranca, config=None):
    """Link wa.me com a mensagem pronta. O envio é manual, dentro do WhatsApp."""
    telefone = telefone_whatsapp(cobranca.associado.contato)
    if not telefone or not cobranca.em_aberto:
        return None
    texto = quote(mensagem_whatsapp(cobranca, config), safe="")
    return f"https://wa.me/{telefone}?text={texto}"
