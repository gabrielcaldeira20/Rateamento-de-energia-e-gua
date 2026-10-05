from django.contrib import admin

from .models import Associado


@admin.register(Associado)
class AssociadoAdmin(admin.ModelAdmin):
    list_display = ["nome", "contato", "ativo", "rede_sede", "rede_poco", "agua_ligada"]
    list_filter = ["ativo", "rede_sede", "rede_poco", "agua_ligada"]
    search_fields = ["nome"]
