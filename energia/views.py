"""Lançamento de energia em 3 passos. Os dados entre os passos ficam na sessão."""
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect, render
from django.views import View

from associados.services import elegiveis_energia
from core.models import Configuracao
from core.utils import mes_atual, mes_iso

from . import services
from .forms import ContaForm
from .models import FechamentoEnergia, Rede

CHAVE = "energia_lancamento"


def ler_sessao(request):
    dados = request.session.get(CHAVE)
    if not dados:
        return None
    return {
        "rede": dados["rede"],
        "competencia": date.fromisoformat(dados["competencia"]),
        "vencimento": date.fromisoformat(dados["vencimento"]),
        "valor_total": Decimal(dados["valor_total"]),
        "kwh_total": int(dados["kwh_total"]),
        "leituras": {int(k): v for k, v in dados.get("leituras", {}).items()},
    }


def gravar_sessao(request, conta, leituras=None):
    request.session[CHAVE] = {
        "rede": conta["rede"],
        "competencia": conta["competencia"].isoformat(),
        "vencimento": conta["vencimento"].isoformat(),
        "valor_total": str(conta["valor_total"]),
        "kwh_total": conta["kwh_total"],
        "leituras": {str(k): v for k, v in (leituras or {}).items()},
    }


def ler_inteiro(texto):
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        valor = int(Decimal(texto.replace(",", ".")))
    except Exception:
        return None
    return valor if valor >= 0 else None


class Passo1View(LoginRequiredMixin, View):
    template = "energia/passo1.html"

    def contexto(self, form):
        return {
            "form": form, "passo": 1,
            "fechamentos": FechamentoEnergia.objects.all()[:12],
        }

    def get(self, request):
        conta = ler_sessao(request)
        if conta and request.GET.get("voltar"):
            inicial = {**conta, "competencia": mes_iso(conta["competencia"])}
        else:
            competencia = mes_atual()
            inicial = {"rede": Rede.SEDE, "competencia": mes_iso(competencia),
                       "vencimento": services.vencimento_padrao(competencia)}
        return render(request, self.template, self.contexto(ContaForm(initial=inicial)))

    def post(self, request):
        form = ContaForm(request.POST)
        if not form.is_valid():
            return render(request, self.template, self.contexto(form))
        anterior = ler_sessao(request)
        mesma_conta = anterior and anterior["rede"] == form.cleaned_data["rede"] and anterior["competencia"] == form.cleaned_data["competencia"]
        gravar_sessao(request, form.cleaned_data, anterior["leituras"] if mesma_conta else None)
        return redirect("energia:passo2")


class Passo2View(LoginRequiredMixin, View):
    """Tabela de leituras: anterior somente leitura, atual editável."""

    def get(self, request):
        conta = ler_sessao(request)
        if not conta:
            return redirect("energia:passo1")
        linhas = []
        for associado in elegiveis_energia(conta["rede"], conta["competencia"]):
            linhas.append({
                "associado": associado,
                "anterior": services.leitura_anterior(associado, conta["rede"]),
                "atual": conta["leituras"].get(associado.pk),
            })
        contexto = {
            "passo": 2, "conta": conta, "rede_label": Rede(conta["rede"]).label, "linhas": linhas,
            "fator": services.calcular_fator(conta["valor_total"], conta["kwh_total"]),
            "config": Configuracao.atual(),
        }
        return render(request, "energia/passo2.html", contexto)

    def post(self, request):
        conta = ler_sessao(request)
        if not conta:
            return redirect("energia:passo1")
        leituras = {}
        for associado in elegiveis_energia(conta["rede"], conta["competencia"]):
            leituras[associado.pk] = ler_inteiro(request.POST.get(f"leitura_{associado.pk}"))
        gravar_sessao(request, conta, leituras)
        return redirect("energia:passo3")


class Passo3View(LoginRequiredMixin, View):
    """Revisão: fator, perda, avisos e confirmação."""

    def rateio(self, conta):
        return services.calcular_rateio(
            conta["rede"], conta["competencia"], conta["valor_total"], conta["kwh_total"], conta["leituras"],
        )

    def get(self, request):
        conta = ler_sessao(request)
        if not conta:
            return redirect("energia:passo1")
        contexto = {"passo": 3, "conta": conta, "rede_label": Rede(conta["rede"]).label, "rateio": self.rateio(conta)}
        return render(request, "energia/passo3.html", contexto)

    def post(self, request):
        conta = ler_sessao(request)
        if not conta:
            return redirect("energia:passo1")
        try:
            resultado = services.fechar_energia(
                conta["rede"], conta["competencia"], conta["valor_total"], conta["kwh_total"],
                conta["vencimento"], conta["leituras"],
            )
        except services.FechamentoInvalido as erro:
            for texto in erro.erros:
                messages.error(request, texto)
            return redirect("energia:passo3")
        del request.session[CHAVE]
        request.session["energia_resultado"] = {
            "fechamento": resultado.fechamento.pk,
            "qtd": resultado.qtd_cobrancas, "total": str(resultado.total_cobrancas),
            "qtd_multas": resultado.qtd_multas, "total_multas": str(resultado.total_multas),
        }
        return redirect("energia:concluido")


class ConcluidoView(LoginRequiredMixin, View):
    def get(self, request):
        resultado = request.session.pop("energia_resultado", None)
        if not resultado:
            return redirect("energia:passo1")
        resultado["fechamento"] = FechamentoEnergia.objects.get(pk=resultado["fechamento"])
        resultado["total"] = Decimal(resultado["total"])
        resultado["total_multas"] = Decimal(resultado["total_multas"])
        return render(request, "energia/concluido.html", {"passo": 4, "r": resultado})


class CancelarView(LoginRequiredMixin, View):
    def post(self, request):
        request.session.pop(CHAVE, None)
        return redirect("energia:passo1")
