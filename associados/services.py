from django.db.models import Q

from .models import Associado


def filtrar(busca="", rede="todas", agua="todos", status="ativos"):
    """Filtros da lista de associados, os mesmos do protótipo."""
    qs = Associado.objects.all()
    if status == "ativos":
        qs = qs.filter(ativo=True)
    elif status == "inativos":
        qs = qs.filter(ativo=False)
    if busca:
        qs = qs.filter(nome__icontains=busca)
    if rede == "sede":
        qs = qs.filter(rede_sede=True)
    elif rede == "poco":
        qs = qs.filter(rede_poco=True)
    if agua == "ligada":
        qs = qs.filter(agua_ligada=True)
    elif agua == "desligada":
        qs = qs.filter(agua_ligada=False)
    return qs


def elegiveis_energia(rede):
    """Associados que entram no rateio: ativos, com a rede e com o padrão ligado."""
    if rede == "SEDE":
        filtro = Q(rede_sede=True, padrao_ligado_sede=True)
    else:
        filtro = Q(rede_poco=True, padrao_ligado_poco=True)
    return Associado.objects.filter(filtro, ativo=True).order_by("nome", "pk")


def definir_ativo(associado, ativo):
    """Inativar não apaga: o histórico continua nas consultas."""
    associado.ativo = ativo
    associado.save(update_fields=["ativo"])
