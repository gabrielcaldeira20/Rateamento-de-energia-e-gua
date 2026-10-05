from decimal import Decimal

from django import forms

from core.forms import BootstrapMixin
from core.utils import mes_label, parse_mes

from . import services
from .models import Rede


class ContaForm(BootstrapMixin, forms.Form):
    """Passo 1: dados da conta da concessionária."""

    rede = forms.ChoiceField(choices=Rede.choices)
    competencia = forms.CharField(label="Mês de competência", widget=forms.TextInput(attrs={"type": "month"}))
    vencimento = forms.DateField(label="Data de vencimento", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    valor_total = forms.DecimalField(label="Valor total da conta (R$)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    kwh_total = forms.IntegerField(label="kWh total da conta", min_value=1)

    def clean_competencia(self):
        competencia = parse_mes(self.cleaned_data["competencia"])
        if not competencia:
            raise forms.ValidationError("Informe o mês no formato AAAA-MM.")
        return competencia

    def clean(self):
        dados = super().clean()
        rede, competencia = dados.get("rede"), dados.get("competencia")
        if rede and competencia and services.ja_fechado(rede, competencia):
            raise forms.ValidationError(
                f"Já existe fechamento para a rede {Rede(rede).label} em {mes_label(competencia)}. "
                "Escolha outro mês para evitar cobranças duplicadas."
            )
        return dados
