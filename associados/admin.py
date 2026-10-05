from django.contrib import admin

from .models import Associado, HistoricoLigacao


class HistoricoInline(admin.TabularInline):
    model = HistoricoLigacao
    extra = 0
    can_delete = False
    readonly_fields = ["tipo", "ligado", "data", "observacao"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Associado)
class AssociadoAdmin(admin.ModelAdmin):
    list_display = ["nome", "contato", "ativo", "rede_sede", "rede_poco", "agua_ligada"]
    list_filter = ["ativo", "rede_sede", "rede_poco", "agua_ligada"]
    search_fields = ["nome"]
    # Reflexo do histórico de ligações: mude pelo sistema, não pelo admin.
    readonly_fields = ["rede_sede", "rede_poco", "agua_ligada"]
    inlines = [HistoricoInline]
