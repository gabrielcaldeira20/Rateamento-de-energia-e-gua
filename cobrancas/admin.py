from django.contrib import admin

from .models import Cobranca, MovimentoCredito, Pagamento


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0
    readonly_fields = ["valor", "data", "observacao", "lote"]
    can_delete = False


@admin.register(Cobranca)
class CobrancaAdmin(admin.ModelAdmin):
    list_display = ["associado", "tipo", "rede", "competencia", "valor", "valor_pago", "status"]
    list_filter = ["tipo", "rede", "status", "competencia"]
    search_fields = ["associado__nome"]
    inlines = [PagamentoInline]


admin.site.register(MovimentoCredito)
