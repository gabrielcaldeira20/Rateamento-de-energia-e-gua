"""Atalhos para criar dados nos testes."""
from decimal import Decimal

from django.contrib.auth import get_user_model

from associados.models import Associado


def tesoureiro():
    return get_user_model().objects.create_user("tesoureiro", password="senha-forte-123")


def associado(nome="Maria", sede=True, poco=False, **extra):
    dados = {
        "nome": nome,
        "contato": "(38) 99999-0000",
        "valor_mensalidade": Decimal("40.00"),
        "rede_sede": sede,
        "padrao_ligado_sede": sede,
        "leitura_inicial_sede": 1000 if sede else None,
        "rede_poco": poco,
        "padrao_ligado_poco": poco,
        "leitura_inicial_poco": 500 if poco else None,
    }
    dados.update(extra)
    return Associado.objects.create(**dados)
