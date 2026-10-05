"""Funções pequenas usadas em vários apps: dinheiro, meses e datas."""
import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.utils import timezone

CENTAVO = Decimal("0.01")
MESES_ABREV = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


def arredondar(valor, casas=CENTAVO):
    """Arredonda meio para cima (ROUND_HALF_UP), padrão para valores em reais."""
    return Decimal(valor).quantize(casas, rounding=ROUND_HALF_UP)


def formatar_brl(valor, simbolo=True):
    """Formata Decimal no padrão brasileiro: 1.234,56."""
    valor = arredondar(valor or Decimal("0"))
    sinal = "-" if valor < 0 else ""
    inteiro, centavos = f"{abs(valor):.2f}".split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    texto = f"{sinal}{inteiro},{centavos}"
    return f"R$ {texto}" if simbolo else texto


def hoje():
    return timezone.localdate()


def primeiro_dia(d):
    return date(d.year, d.month, 1)


def ultimo_dia(d):
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def somar_meses(d, n):
    """Primeiro dia do mês que fica n meses depois (ou antes) de d."""
    total = d.year * 12 + (d.month - 1) + n
    return date(total // 12, total % 12 + 1, 1)


def mes_atual():
    return primeiro_dia(hoje())


def parse_mes(texto, padrao=None):
    """Converte 'AAAA-MM' no primeiro dia do mês. Retorna padrao se inválido."""
    try:
        ano, mes = str(texto).split("-")[:2]
        return date(int(ano), int(mes), 1)
    except (ValueError, TypeError):
        return padrao


def mes_iso(d):
    return f"{d.year:04d}-{d.month:02d}"


def mes_label(d):
    """'jun/2026', como no protótipo."""
    return f"{MESES_ABREV[d.month - 1]}/{d.year}"


def meses_entre(inicio, fim):
    """Lista do primeiro dia de cada mês de inicio a fim, inclusive."""
    atual, saida = primeiro_dia(inicio), []
    while atual <= fim:
        saida.append(atual)
        atual = somar_meses(atual, 1)
    return saida
