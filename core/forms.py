from django import forms

from .models import Configuracao


class BootstrapMixin:
    """Aplica as classes do Bootstrap 5 nos widgets do formulário."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, forms.CheckboxInput):
                classe = "form-check-input"
            elif isinstance(widget, forms.Select):
                classe = "form-select"
            else:
                classe = "form-control"
            widget.attrs["class"] = (widget.attrs.get("class", "") + " " + classe).strip()


class ConfiguracaoForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Configuracao
        fields = [
            "nome_associacao", "chave_pix", "taxa_disponibilidade", "valor_agua",
            "limite_kwh_multa", "percentual_multa",
        ]
        help_texts = {
            "chave_pix": "Aparece na mensagem de lembrete pelo WhatsApp.",
            "taxa_disponibilidade": "Somada a cada cobrança de energia, por rede ligada. A Associação não paga.",
            "limite_kwh_multa": "Consumo estritamente acima deste valor gera multa.",
            "percentual_multa": "Aplicado sobre o valor da energia, sem a taxa de disponibilidade.",
        }
