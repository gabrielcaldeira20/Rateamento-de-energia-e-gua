from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from django.utils.dateparse import parse_date as _parse_date

from . import services
from .forms import AssociadoForm, HistoricoForm
from .models import Associado, HistoricoLigacao, TipoLigacao


def parse_date(texto):
    try:
        return _parse_date(texto)
    except ValueError:
        return None


class ListaView(LoginRequiredMixin, View):
    def get(self, request):
        filtros = {
            "busca": request.GET.get("busca", "").strip(),
            "rede": request.GET.get("rede", "todas"),
            "agua": request.GET.get("agua", "todos"),
            "status": request.GET.get("status", "ativos"),
        }
        lista = list(services.filtrar(**filtros))
        contexto = {
            "linhas": self.linhas(lista),
            "filtros": filtros,
            "total": Associado.objects.count(),
        }
        return render(request, "associados/lista.html", contexto)

    def linhas(self, lista):
        """Cada linha da tabela com o saldo devedor calculado pelo app de cobranças."""
        try:
            from cobrancas.services import saldos_devedores
        except ImportError:
            return [{"a": a, "saldo": None} for a in lista]
        saldos = saldos_devedores([a.pk for a in lista])
        return [{"a": a, "saldo": saldos.get(a.pk)} for a in lista]


class FormularioView(LoginRequiredMixin, View):
    template = "associados/form.html"

    def objeto(self, pk):
        return get_object_or_404(Associado, pk=pk) if pk else None

    def get(self, request, pk=None):
        return render(request, self.template, {"form": AssociadoForm(instance=self.objeto(pk)), "editando": pk})

    def post(self, request, pk=None):
        form = AssociadoForm(request.POST, instance=self.objeto(pk))
        if form.is_valid():
            try:
                associado = form.save()
            except services.ErroHistorico as erro:
                form.add_error(None, erro.messages)
                return render(request, self.template, {"form": form, "editando": pk})
            acao = "atualizado" if pk else "cadastrado"
            messages.success(request, f"{associado.nome} {acao}.")
            return redirect("associados:lista")
        return render(request, self.template, {"form": form, "editando": pk})


class DetalheView(LoginRequiredMixin, View):
    def get(self, request, pk):
        associado = get_object_or_404(Associado, pk=pk)
        contexto = {"a": associado}
        try:
            from cobrancas.services import resumo_associado
        except ImportError:
            resumo_associado = None
        if resumo_associado:
            contexto.update(resumo_associado(associado))
        return render(request, "associados/detalhe.html", contexto)


class AtivoView(LoginRequiredMixin, View):
    ativo = True

    def post(self, request, pk):
        associado = get_object_or_404(Associado, pk=pk)
        services.definir_ativo(associado, self.ativo)
        texto = "reativado" if self.ativo else "marcado como inativo"
        messages.success(request, f"{associado.nome} {texto}.")
        return redirect("associados:lista")


# ---------------------------------------------------------------- histórico de ligações

class HistoricoAssociadoView(LoginRequiredMixin, View):
    """Linha do tempo de um associado, com inclusão de registros retroativos."""

    template = "associados/historico_associado.html"

    def contexto(self, associado, form):
        return {
            "a": associado,
            "form": form,
            "registros": associado.historico_ligacoes.order_by("-data", "tipo", "-pk"),
        }

    def get(self, request, pk):
        associado = get_object_or_404(Associado, pk=pk)
        return render(request, self.template, self.contexto(associado, HistoricoForm(associado=associado)))

    def post(self, request, pk):
        associado = get_object_or_404(Associado, pk=pk)
        form = HistoricoForm(request.POST, associado=associado)
        if form.is_valid():
            d = form.cleaned_data
            try:
                services.salvar_registro(
                    associado, d["tipo"], d["ligado"], d["data"], d["observacao"], leitura_inicial=d["leitura_inicial"],
                )
            except services.ErroHistorico as erro:
                form.add_error(None, erro.messages)
            else:
                messages.success(request, "Registro salvo. O estado atual do associado foi recalculado.")
                return redirect("associados:historico", pk=associado.pk)
        return render(request, self.template, self.contexto(associado, form))


class HistoricoEditarView(LoginRequiredMixin, View):
    template = "associados/historico_form.html"

    def get(self, request, pk):
        registro = get_object_or_404(HistoricoLigacao, pk=pk)
        return render(request, self.template, {"registro": registro, "form": HistoricoForm.do_registro(registro)})

    def post(self, request, pk):
        registro = get_object_or_404(HistoricoLigacao, pk=pk)
        form = HistoricoForm(request.POST, associado=registro.associado)
        if form.is_valid():
            d = form.cleaned_data
            try:
                services.salvar_registro(
                    registro.associado, d["tipo"], d["ligado"], d["data"], d["observacao"],
                    registro=registro, leitura_inicial=d["leitura_inicial"],
                )
            except services.ErroHistorico as erro:
                form.add_error(None, erro.messages)
            else:
                messages.success(request, "Registro atualizado. O estado atual do associado foi recalculado.")
                return redirect("associados:historico", pk=registro.associado_id)
        return render(request, self.template, {"registro": registro, "form": form})


class HistoricoExcluirView(LoginRequiredMixin, View):
    def post(self, request, pk):
        registro = get_object_or_404(HistoricoLigacao, pk=pk)
        associado_id = registro.associado_id
        try:
            services.excluir_registro(registro)
        except services.ErroHistorico as erro:
            messages.error(request, " ".join(erro.messages))
        else:
            messages.success(request, "Registro excluído. O estado atual do associado foi recalculado.")
        return redirect("associados:historico", pk=associado_id)


class HistoricoListaView(LoginRequiredMixin, View):
    """Lista geral do histórico, filtrável por associado, tipo e período."""

    def get(self, request):
        filtros = {
            "associado": request.GET.get("associado", ""),
            "tipo": request.GET.get("tipo", "todos"),
            "de": request.GET.get("de", ""),
            "ate": request.GET.get("ate", ""),
        }
        qs = HistoricoLigacao.objects.select_related("associado").order_by("-data", "associado__nome", "tipo")
        if filtros["associado"].isdigit():
            qs = qs.filter(associado_id=int(filtros["associado"]))
        if filtros["tipo"] in TipoLigacao.values:
            qs = qs.filter(tipo=filtros["tipo"])
        de, ate = parse_date(filtros["de"] or ""), parse_date(filtros["ate"] or "")
        if de:
            qs = qs.filter(data__gte=de)
        if ate:
            qs = qs.filter(data__lte=ate)
        contexto = {
            "registros": qs,
            "filtros": filtros,
            "associados": Associado.objects.order_by("nome"),
            "tipos": TipoLigacao.choices,
        }
        return render(request, "associados/historico_lista.html", contexto)
