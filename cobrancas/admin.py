from django.contrib import admin

from .models import Cobranca, MovimentoCredito, Pagamento

# valor_pago, status, pagamentos e créditos são consequência de cobrancas.services
# (registrar_pagamento e baixar_em_lote). Alterá-los aqui deixaria a cobrança, o pagamento
# e o crédito discordando entre si. Pagamentos se registram pela tela de Cobranças.


class PagamentoInline(admin.TabularInline):
    model = Pagamento
    extra = 0
    readonly_fields = ["valor", "data", "observacao", "lote"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cobranca)
class CobrancaAdmin(admin.ModelAdmin):
    list_display = ["associado", "tipo", "rede", "competencia", "valor", "valor_pago", "status"]
    list_filter = ["tipo", "rede", "status", "competencia"]
    search_fields = ["associado__nome"]
    readonly_fields = ["valor_pago", "status"]
    inlines = [PagamentoInline]


@admin.register(MovimentoCredito)
class MovimentoCreditoAdmin(admin.ModelAdmin):
    """Somente consulta: o crédito nasce do excedente de um pagamento."""

    list_display = ["associado", "valor", "data", "pagamento"]
    search_fields = ["associado__nome"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
