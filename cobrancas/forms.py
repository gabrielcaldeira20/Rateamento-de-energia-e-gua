from decimal import Decimal

from django import forms

from core.utils import hoje


class PagamentoForm(forms.Form):
    valor = forms.DecimalField(label="Valor pago (R$)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    data = forms.DateField(label="Data do pagamento", initial=hoje)
    observacao = forms.CharField(label="Observação", max_length=200, required=False)
