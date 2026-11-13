from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from core.models import Configuracao
from core.utils import formatar_brl, mes_atual, mes_iso, mes_label, parse_mes

from . import services
from .forms import PagamentoForm
from .models import Cobranca, StatusCobranca


def voltar_para_lista(request):
    """Volta para a lista mantendo os filtros que estavam na tela."""
    filtros = request.POST.get("filtros", "")
    return redirect(f"{reverse('cobrancas:lista')}?{filtros}" if filtros else reverse("cobrancas:lista"))


class ListaView(LoginRequiredMixin, View):
    def get(self, request):
        filtros = {
            "busca": request.GET.get("busca", "").strip(),
            "tipo": request.GET.get("tipo", "todos"),
            "mes": request.GET.get("mes", "todos"),
            "status": request.GET.get("status", StatusCobranca.PENDENTE),
        }
        competencia = parse_mes(filtros["mes"]) if filtros["mes"] != "todos" else None
        lista = list(services.filtrar(filtros["busca"], filtros["tipo"], competencia, filtros["status"]))
        abertas = [c for c in lista if c.em_aberto]
        meses = Cobranca.objects.dates("competencia", "month", order="DESC")
        config = Configuracao.atual()
        contexto = {
            "lista": lista,
            "filtros": filtros,
            "filtros_query": request.GET.urlencode(),
            "qtd_abertas": len(abertas),
            "total_aberto": sum((c.saldo for c in abertas), services.ZERO),
            "tipos": services.TIPOS_FILTRO,
            "status_opcoes": StatusCobranca.choices,
            "meses": [(mes_iso(m), mes_label(m)) for m in meses],
            "mes_atual": mes_iso(mes_atual()),
            "links_whatsapp": {c.pk: services.link_whatsapp(c, config) for c in abertas},
            "sem_chave_pix": not config.chave_pix,
        }
        return render(request, "cobrancas/lista.html", contexto)


class PagarView(LoginRequiredMixin, View):
    def post(self, request, pk):
        cobranca = get_object_or_404(Cobranca, pk=pk)
        form = PagamentoForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Pagamento não registrado: informe um valor maior que zero e uma data válida.")
            return voltar_para_lista(request)
        try:
            resultado = services.registrar_pagamento(
                cobranca.pk, form.cleaned_data["valor"], form.cleaned_data["data"], form.cleaned_data["observacao"],
            )
        except services.PagamentoInvalido as erro:
            messages.error(request, str(erro))
            return voltar_para_lista(request)
        cobranca.refresh_from_db()
        texto = f"Pagamento registrado para {cobranca.associado.nome}."
        if cobranca.status == StatusCobranca.PARCIAL:
            texto += f" Pagamento parcial: restam {formatar_brl(cobranca.saldo)}."
        if resultado.credito_gerado > 0:
            texto += f" Crédito de {formatar_brl(resultado.credito_gerado)} gerado."
        messages.success(request, texto)
        return voltar_para_lista(request)


class LoteView(LoginRequiredMixin, View):
    def post(self, request):
        ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
        if not ids:
            messages.error(request, "Nenhuma cobrança selecionada.")
            return voltar_para_lista(request)
        qtd, total, _ = services.baixar_em_lote(ids)
        messages.success(request, f"{qtd} cobrança(s) marcada(s) como paga(s), total de {formatar_brl(total)}.")
        return voltar_para_lista(request)


class GerarMensaisView(LoginRequiredMixin, View):
    def post(self, request):
        competencia = parse_mes(request.POST.get("competencia"), mes_atual())
        r = services.gerar_mensais(competencia)
        rotulo = mes_label(competencia)
        if r.criadas == 0:
            messages.info(request, f"Nenhuma cobrança nova para {rotulo}: {r.existentes} já existiam.")
        else:
            messages.success(
                request,
                f"{r.criadas} cobrança(s) de mensalidade e água criada(s) para {rotulo} "
                f"({formatar_brl(r.total_criado)}). {r.existentes} já existiam.",
            )
        return voltar_para_lista(request)
