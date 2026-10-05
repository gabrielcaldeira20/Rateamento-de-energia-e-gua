from django import template

register = template.Library()


@register.filter
def pegar(dicionario, chave):
    return dicionario.get(chave) if dicionario else None
