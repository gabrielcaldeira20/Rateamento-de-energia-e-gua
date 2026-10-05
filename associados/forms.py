from django import forms
from django.db import transaction

from core.forms import BootstrapMixin
from core.utils import hoje

from .models import CAMPO_DO_TIPO, Associado, TipoLigacao
from .services import recalcular_estado, registrar_mudanca


class AssociadoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Associado
        fields = [
            "nome", "contato", "endereco", "valor_mensalidade", "e_associacao",
            "rede_sede", "padrao_ligado_sede", "leitura_inicial_sede",
            "rede_poco", "padrao_ligado_poco", "leitura_inicial_poco",
            "agua_ligada",
        ]
        widgets = {"contato": forms.TextInput(attrs={"placeholder": "(38) 99999-9999"})}
        help_texts = {
            "leitura_inicial_sede": "Obrigatória ao ativar a rede. Base do primeiro lançamento de energia.",
            "leitura_inicial_poco": "Obrigatória ao ativar a rede. Base do primeiro lançamento de energia.",
        }

    data_mudanca = forms.DateField(
        label="Data da mudança", required=False, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="Data em que as mudanças de rede ou água valem. Aceita datas passadas.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["data_mudanca"].initial = hoje()
        if not self.instance.pk:
            self.fields["data_mudanca"].label = "Ligado desde"
            self.fields["data_mudanca"].help_text = "Data em que os serviços marcados foram ligados. Aceita datas passadas."

    def clean_data_mudanca(self):
        data = self.cleaned_data.get("data_mudanca") or hoje()
        if data > hoje():
            raise forms.ValidationError("A data não pode estar no futuro.")
        return data

    def save(self, commit=True):
        """Salva o associado e registra no histórico cada serviço ligado ou desligado.

        No cadastro, grava um registro por serviço ligado. Na edição, só os que mudaram.
        Depois, os campos de rede e água passam a refletir o registro mais recente por data.
        """
        novo = self.instance.pk is None
        data = self.cleaned_data.get("data_mudanca") or hoje()
        with transaction.atomic():
            associado = super().save(commit=True)
            for tipo, campo in CAMPO_DO_TIPO.items():
                estado = getattr(associado, campo)
                if novo:
                    if estado:
                        registrar_mudanca(associado, tipo, True, data, "Cadastro do associado")
                elif estado != bool(self.initial.get(campo)):
                    texto = "Ligado no cadastro" if estado else "Desligado no cadastro"
                    registrar_mudanca(associado, tipo, estado, data, texto)
            recalcular_estado(associado)
        return associado

    def clean(self):
        dados = super().clean()
        for rede, rotulo in (("sede", "Sede"), ("poco", "Poço")):
            if dados.get(f"rede_{rede}"):
                if dados.get(f"leitura_inicial_{rede}") is None:
                    self.add_error(
                        f"leitura_inicial_{rede}",
                        f"Informe a leitura atual do medidor ({rotulo}) para ativar a rede.",
                    )
            else:
                # Sem a rede, o padrão não pode estar ligado.
                dados[f"padrao_ligado_{rede}"] = False
        return dados


class HistoricoForm(BootstrapMixin, forms.Form):
    """Registro do histórico de ligações, inclusive retroativo."""

    tipo = forms.ChoiceField(label="Serviço", choices=TipoLigacao.choices)
    ligado = forms.TypedChoiceField(
        label="Novo estado", choices=[("1", "Ligado"), ("0", "Desligado")], coerce=lambda v: v == "1",
    )
    data = forms.DateField(label="Data", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    observacao = forms.CharField(label="Observação", max_length=200, required=False)
    leitura_inicial = forms.IntegerField(
        label="Leitura inicial do medidor", min_value=0, required=False,
        help_text="Obrigatória ao ligar uma rede de associado que ainda não tem leitura inicial.",
    )

    def __init__(self, *args, associado=None, **kwargs):
        self.associado = associado
        super().__init__(*args, **kwargs)
        self.fields["data"].initial = hoje()

    def clean_data(self):
        data = self.cleaned_data["data"]
        if data > hoje():
            raise forms.ValidationError("A data não pode estar no futuro.")
        return data

    def clean(self):
        dados = super().clean()
        tipo, ligado = dados.get("tipo"), dados.get("ligado")
        if self.associado and tipo in ("SEDE", "POCO") and ligado:
            if self.associado.leitura_inicial(tipo) is None and dados.get("leitura_inicial") is None:
                self.add_error("leitura_inicial", "Informe a leitura inicial do medidor para ligar a rede.")
        return dados

    @classmethod
    def do_registro(cls, registro):
        return cls(associado=registro.associado, initial={
            "tipo": registro.tipo, "ligado": "1" if registro.ligado else "0",
            "data": registro.data, "observacao": registro.observacao,
        })
