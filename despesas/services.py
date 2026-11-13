from core.utils import somar

from .models import Despesa


def filtrar(competencia=None, categoria="todas"):
    qs = Despesa.objects.all()
    if competencia:
        qs = qs.filter(competencia=competencia)
    if categoria and categoria != "todas":
        qs = qs.filter(categoria=categoria)
    return qs


def total(qs):
    return somar(qs, "valor")
