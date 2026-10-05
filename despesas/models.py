from django.db import models
from django.db.models import Q


class Categoria(models.TextChoices):
    MANUTENCAO = "MANUTENCAO", "Manutenção"
    MATERIAL = "MATERIAL", "Material"
    CONTA_ENERGIA = "CONTA_ENERGIA", "Conta de energia"
    FOLHA = "FOLHA", "Folha de pagamento"
    COMBUSTIVEL = "COMBUSTIVEL", "Combustível"
    DOCUMENTOS = "DOCUMENTOS", "Documentos"
    LIMPEZA = "LIMPEZA", "Limpeza"
    OUTRA = "OUTRA", "Outra"


class Despesa(models.Model):
    descricao = models.CharField("descrição", max_length=200)
    categoria = models.CharField(max_length=14, choices=Categoria.choices)
    categoria_outra = models.CharField("descreva a categoria", max_length=80, blank=True)
    valor = models.DecimalField("valor (R$)", max_digits=12, decimal_places=2)
    data = models.DateField()
    competencia = models.DateField("competência", help_text="Sempre o 1º dia do mês.")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-competencia", "-data", "-pk"]
        constraints = [
            models.CheckConstraint(condition=Q(valor__gt=0), name="despesa_valor_positivo"),
            models.CheckConstraint(
                condition=~Q(categoria="OUTRA") | ~Q(categoria_outra=""), name="despesa_outra_exige_texto",
            ),
        ]

    def __str__(self):
        return self.descricao

    @property
    def rotulo_categoria(self):
        if self.categoria == Categoria.OUTRA:
            return self.categoria_outra
        return self.get_categoria_display()
