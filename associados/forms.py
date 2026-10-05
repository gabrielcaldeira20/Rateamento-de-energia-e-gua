from django import forms

from core.forms import BootstrapMixin

from .models import Associado


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
