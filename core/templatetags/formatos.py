from django import template

from core import utils

register = template.Library()


@register.filter
def brl(valor):
    return utils.formatar_brl(valor)


@register.filter
def mes(valor):
    return utils.mes_label(valor) if valor else ""


@register.filter
def mes_iso(valor):
    return utils.mes_iso(valor) if valor else ""
