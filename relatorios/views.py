from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, HttpResponseBadRequest
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


class ExportarView(LoginRequiredMixin, View):
    """Exporta o relatório com o regime e o período selecionados na tela.

    /relatorios/financeiro/exportar/?formato=pdf|csv&regime=pagamento|competencia&inicio=AAAA-MM&fim=AAAA-MM
    """

    def get(self, request):
        from .exportacao import gerar_csv, gerar_pdf, montar

        formato = request.GET.get("formato", "")
        if formato not in ("pdf", "csv"):
            return HttpResponseBadRequest("Formato inválido. Use pdf ou csv.")
        regime = request.GET.get("regime", "pagamento")
        if regime not in dict(services.MODOS):
            regime = "pagamento"
        inicio, fim = services.resolver_periodo(
            "custom", parse_mes(request.GET.get("inicio")), parse_mes(request.GET.get("fim")),
        )
        dados = montar(inicio, fim, regime)
        if formato == "csv":
            resposta = HttpResponse(gerar_csv(dados), content_type="text/csv; charset=utf-8")
        else:
            resposta = HttpResponse(gerar_pdf(dados), content_type="application/pdf")
        resposta["Content-Disposition"] = f'attachment; filename="{dados.nome_arquivo}.{formato}"'
        return resposta
