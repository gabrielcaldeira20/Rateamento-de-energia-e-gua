"""Carga inicial do histórico de ligações a partir do estado atual dos associados.

Para cada serviço ligado hoje, cria um registro "ligado" na menor data entre:
- a data de criação do associado;
- a competência mais antiga de qualquer leitura ou cobrança dele.
Assim nenhum associado sai do rateio de meses passados. Fechamentos e cobranças não são alterados.
A reversão apaga os registros de histórico.
"""
from django.db import migrations
from django.utils import timezone

CAMPOS = (("SEDE", "rede_sede"), ("POCO", "rede_poco"), ("AGUA", "agua_ligada"))


def carregar(apps, schema_editor):
    Associado = apps.get_model("associados", "Associado")
    HistoricoLigacao = apps.get_model("associados", "HistoricoLigacao")
    Leitura = apps.get_model("energia", "Leitura")
    Cobranca = apps.get_model("cobrancas", "Cobranca")
    alias = schema_editor.connection.alias

    for associado in Associado.objects.using(alias).all():
        datas = [timezone.localtime(associado.criado_em).date()]
        leitura = (
            Leitura.objects.using(alias).filter(associado_id=associado.pk)
            .order_by("fechamento__competencia").values_list("fechamento__competencia", flat=True).first()
        )
        cobranca = (
            Cobranca.objects.using(alias).filter(associado_id=associado.pk)
            .order_by("competencia").values_list("competencia", flat=True).first()
        )
        datas += [d for d in (leitura, cobranca) if d]
        data = min(datas)
        for tipo, campo in CAMPOS:
            if getattr(associado, campo):
                HistoricoLigacao.objects.using(alias).get_or_create(
                    associado_id=associado.pk, tipo=tipo, data=data,
                    defaults={"ligado": True, "observacao": "Carga inicial do histórico"},
                )


def desfazer(apps, schema_editor):
    HistoricoLigacao = apps.get_model("associados", "HistoricoLigacao")
    HistoricoLigacao.objects.using(schema_editor.connection.alias).all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("associados", "0002_historico_ligacao"),
        ("energia", "0001_initial"),
        ("cobrancas", "0002_initial"),
    ]

    operations = [migrations.RunPython(carregar, desfazer)]
