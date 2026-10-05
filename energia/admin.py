from django.contrib import admin

from .models import FechamentoEnergia, Leitura


class LeituraInline(admin.TabularInline):
    model = Leitura
    extra = 0
    readonly_fields = ["associado", "leitura_anterior", "leitura_atual", "consumo_kwh", "valor_energia"]
    can_delete = False


@admin.register(FechamentoEnergia)
class FechamentoAdmin(admin.ModelAdmin):
    list_display = ["rede", "competencia", "valor_total", "kwh_total", "fator", "perda_kwh"]
    inlines = [LeituraInline]
