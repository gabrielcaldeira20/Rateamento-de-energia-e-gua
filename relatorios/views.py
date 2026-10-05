from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render
from django.views import View

from core.utils import mes_iso, parse_mes

from . import services


class FinanceiroView(LoginRequiredMixin, View):
    def get(self, request):
        modo = request.GET.get("modo", "pagamento")
        if modo not in dict(services.MODOS):
            modo = "pagamento"
        preset = request.GET.get("periodo", "6m")
        if preset not in dict(services.PERIODOS):
            preset = "6m"
        inicio, fim = services.resolver_periodo(
            preset, parse_mes(request.GET.get("inicio")), parse_mes(request.GET.get("fim")),
        )
        serie = services.serie_mensal(inicio, fim, modo)
        grafico = {
            "rotulos": [s["mes"] for s in serie],
            "entradas": [float(s["entradas"]) for s in serie],
            "despesas": [float(s["despesas"]) for s in serie],
        }
        contexto = {
            "modo": modo, "preset": preset, "modos": services.MODOS, "periodos": services.PERIODOS,
            "inicio": inicio, "fim": fim, "inicio_iso": mes_iso(inicio), "fim_iso": mes_iso(fim),
            "resumo": services.resumo_periodo(inicio, fim, modo),
            "grafico": grafico,
            "entradas": services.pagamentos_do_periodo(inicio, fim, modo).order_by("-data", "-pk"),
            "despesas": services.despesas_do_periodo(inicio, fim, modo).order_by("-data", "-pk"),
            "disponibilidades": services.disponibilidade_do_periodo(inicio, fim).order_by("-competencia", "associado__nome"),
        }
        return render(request, "relatorios/financeiro.html", contexto)
