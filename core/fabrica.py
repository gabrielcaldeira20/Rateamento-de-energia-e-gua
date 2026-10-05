"""Atalhos para criar dados nos testes."""
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model

from associados.models import CAMPO_DO_TIPO, Associado, HistoricoLigacao


def tesoureiro():
    return get_user_model().objects.create_user("tesoureiro", password="senha-forte-123")


LIGADO_DESDE = date(2000, 1, 1)


def associado(nome="Maria", sede=True, poco=False, ligado_desde=LIGADO_DESDE, **extra):
    """Cria o associado e um registro de histórico "ligado" para cada serviço ligado.

    Com ligado_desde=None, não cria histórico (como um associado gravado fora do formulário).
    """
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
    criado = Associado.objects.create(**dados)
    if ligado_desde:
        for tipo, campo in CAMPO_DO_TIPO.items():
            if getattr(criado, campo):
                HistoricoLigacao.objects.create(associado=criado, tipo=tipo, ligado=True, data=ligado_desde)
    return criado
