from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from core.utils import mes_iso, mes_label, parse_mes

from . import services
from .forms import DespesaForm
from .models import Categoria, Despesa


class ListaView(LoginRequiredMixin, View):
    def get(self, request):
        filtros = {"mes": request.GET.get("mes", "todos"), "categoria": request.GET.get("categoria", "todas")}
        competencia = parse_mes(filtros["mes"]) if filtros["mes"] != "todos" else None
        lista = services.filtrar(competencia, filtros["categoria"])
        meses = Despesa.objects.dates("competencia", "month", order="DESC")
        contexto = {
            "lista": lista,
            "total": services.total(lista),
            "filtros": filtros,
            "categorias": Categoria.choices,
            "meses": [(mes_iso(m), mes_label(m)) for m in meses],
        }
        return render(request, "despesas/lista.html", contexto)


class FormularioView(LoginRequiredMixin, View):
    template = "despesas/form.html"

    def objeto(self, pk):
        return get_object_or_404(Despesa, pk=pk) if pk else None

    def get(self, request, pk=None):
        return render(request, self.template, {"form": DespesaForm(instance=self.objeto(pk)), "editando": pk})

    def post(self, request, pk=None):
        form = DespesaForm(request.POST, instance=self.objeto(pk))
        if form.is_valid():
            despesa = form.save()
            messages.success(request, f"Despesa \"{despesa.descricao}\" salva.")
            return redirect("despesas:lista")
        return render(request, self.template, {"form": form, "editando": pk})


class ExcluirView(LoginRequiredMixin, View):
    def post(self, request, pk):
        despesa = get_object_or_404(Despesa, pk=pk)
        despesa.delete()
        messages.success(request, f"Despesa \"{despesa.descricao}\" excluída.")
        return redirect("despesas:lista")
