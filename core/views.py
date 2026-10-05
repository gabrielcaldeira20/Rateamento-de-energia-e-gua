from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from .forms import ConfiguracaoForm
from .models import Configuracao
from .services import numeros_painel


class PainelView(LoginRequiredMixin, View):
    def get(self, request):
        return render(request, "core/painel.html", {"n": numeros_painel()})


class ConfiguracoesView(LoginRequiredMixin, View):
    template = "core/configuracoes.html"

    def get(self, request):
        form = ConfiguracaoForm(instance=Configuracao.atual())
        return render(request, self.template, {"form": form})

    def post(self, request):
        form = ConfiguracaoForm(request.POST, instance=Configuracao.atual())
        if form.is_valid():
            form.save()
            messages.success(request, "Configurações salvas. Os novos valores valem só para cobranças futuras.")
            return redirect("core:configuracoes")
        return render(request, self.template, {"form": form})
