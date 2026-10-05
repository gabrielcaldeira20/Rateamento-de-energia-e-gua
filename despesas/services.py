from decimal import Decimal

from django.db.models import Sum

from .models import Despesa


def filtrar(competencia=None, categoria="todas"):
    qs = Despesa.objects.all()
    if competencia:
        qs = qs.filter(competencia=competencia)
    if categoria and categoria != "todas":
        qs = qs.filter(categoria=categoria)
    return qs


def total(qs):
    return qs.aggregate(s=Sum("valor"))["s"] or Decimal("0.00")
