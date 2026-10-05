from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from core.utils import ultimo_dia

from .models import CAMPO_DO_TIPO, Associado, HistoricoLigacao


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


def elegiveis_energia(rede, competencia=None):
    """Associados que entram no rateio de uma rede.

    Sem competência: ativos, com a rede e o padrão ligados hoje.
    Com competência: ativos que estavam com a rede ligada no fim do mês, pelo histórico.
    O padrão ligado não tem histórico. Ele só é exigido de quem continua com a rede hoje;
    quem desligou a rede depois da competência entra pelo histórico.
    """
    if competencia is None:
        if rede == "SEDE":
            filtro = Q(rede_sede=True, padrao_ligado_sede=True)
        else:
            filtro = Q(rede_poco=True, padrao_ligado_poco=True)
        return Associado.objects.filter(filtro, ativo=True).order_by("nome", "pk")

    campo_rede = CAMPO_DO_TIPO[rede]
    campo_padrao = "padrao_ligado_sede" if rede == "SEDE" else "padrao_ligado_poco"
    candidatos = Associado.objects.filter(ativo=True, historico_ligacoes__tipo=rede).distinct().order_by("nome", "pk")
    return [
        a for a in candidatos
        if situacao_na_competencia(a, rede, competencia)
        and (getattr(a, campo_padrao) or not getattr(a, campo_rede))
    ]


# ---------------------------------------------------------------- histórico de ligações

class ErroHistorico(ValidationError):
    pass


def situacao_em(associado, tipo, data):
    """Estado do serviço no fim da data: o último registro até ela. Sem registro, desligado."""
    ultimo = (
        HistoricoLigacao.objects.filter(associado=associado, tipo=tipo, data__lte=data)
        .order_by("-data").values_list("ligado", flat=True).first()
    )
    return bool(ultimo)


def situacao_na_competencia(associado, tipo, competencia):
    """Para uma competência, vale o estado no último dia do mês."""
    return situacao_em(associado, tipo, ultimo_dia(competencia))


def recalcular_estado(associado):
    """Atualiza rede_sede, rede_poco e agua_ligada a partir do registro mais recente por data.

    Sem rede, o padrão fica desligado, como no formulário. Ligar uma rede continua
    exigindo leitura inicial.
    """
    for tipo, campo in CAMPO_DO_TIPO.items():
        ultimo = (
            HistoricoLigacao.objects.filter(associado=associado, tipo=tipo)
            .order_by("-data").values_list("ligado", flat=True).first()
        )
        setattr(associado, campo, bool(ultimo))
    for rede, rotulo in (("sede", "Sede"), ("poco", "Poço")):
        if getattr(associado, f"rede_{rede}"):
            if getattr(associado, f"leitura_inicial_{rede}") is None:
                raise ErroHistorico(f"Informe a leitura inicial do medidor ({rotulo}) para ligar a rede.")
        else:
            setattr(associado, f"padrao_ligado_{rede}", False)
    associado.save(update_fields=[
        "rede_sede", "rede_poco", "agua_ligada", "padrao_ligado_sede", "padrao_ligado_poco",
    ])


def registrar_mudanca(associado, tipo, ligado, data, observacao=""):
    """Grava a mudança. Duas mudanças do mesmo tipo na mesma data atualizam o registro."""
    registro, _ = HistoricoLigacao.objects.update_or_create(
        associado=associado, tipo=tipo, data=data,
        defaults={"ligado": ligado, "observacao": observacao},
    )
    return registro


@transaction.atomic
def salvar_registro(associado, tipo, ligado, data, observacao="", registro=None, leitura_inicial=None):
    """Cria (ou edita) um registro, inclusive retroativo, e recalcula o estado atual."""
    if leitura_inicial is not None and tipo in ("SEDE", "POCO"):
        setattr(associado, f"leitura_inicial_{tipo.lower()}", leitura_inicial)
        associado.save(update_fields=[f"leitura_inicial_{tipo.lower()}"])
    if registro is None:
        registro = registrar_mudanca(associado, tipo, ligado, data, observacao)
    else:
        conflito = HistoricoLigacao.objects.filter(associado=associado, tipo=tipo, data=data).exclude(pk=registro.pk)
        if conflito.exists():
            raise ErroHistorico("Já existe um registro deste serviço nesta data. Edite aquele registro.")
        registro.tipo, registro.ligado, registro.data, registro.observacao = tipo, ligado, data, observacao
        registro.save()
    recalcular_estado(associado)
    return registro


@transaction.atomic
def excluir_registro(registro):
    associado = registro.associado
    registro.delete()
    recalcular_estado(associado)


def definir_ativo(associado, ativo):
    """Inativar não apaga: o histórico continua nas consultas."""
    associado.ativo = ativo
    associado.save(update_fields=["ativo"])
