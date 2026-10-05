from decimal import Decimal

from django import forms

from core.forms import BootstrapMixin
from core.utils import hoje, mes_iso, parse_mes, primeiro_dia

from .models import Categoria, Despesa


class DespesaForm(BootstrapMixin, forms.ModelForm):
    competencia = forms.CharField(
        label="Mês de competência", required=False, widget=forms.TextInput(attrs={"type": "month"}),
        help_text="Se ficar vazio, usa o mês da data.",
    )
    valor = forms.DecimalField(label="Valor (R$)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))

    class Meta:
        model = Despesa
        fields = ["descricao", "categoria", "categoria_outra", "valor", "data", "competencia"]
        widgets = {"data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial["competencia"] = mes_iso(self.instance.competencia)
        else:
            self.initial.setdefault("data", hoje())

    def clean_competencia(self):
        texto = self.cleaned_data.get("competencia")
        if not texto:
            return None
        competencia = parse_mes(texto)
        if not competencia:
            raise forms.ValidationError("Informe o mês no formato AAAA-MM.")
        return competencia

    def clean(self):
        dados = super().clean()
        if dados.get("categoria") == Categoria.OUTRA:
            if not (dados.get("categoria_outra") or "").strip():
                self.add_error("categoria_outra", "Descreva a categoria quando escolher \"Outra\".")
        else:
            dados["categoria_outra"] = ""
        if not dados.get("competencia") and dados.get("data"):
            dados["competencia"] = primeiro_dia(dados["data"])
        return dados
