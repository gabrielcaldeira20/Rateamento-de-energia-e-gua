from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Associado(models.Model):
    """Cadastro do associado. Guarda só o estado atual, sem histórico por data."""

    nome = models.CharField(max_length=150)
    contato = models.CharField("contato/WhatsApp", max_length=40)
    endereco = models.CharField("endereço", max_length=200, blank=True)
    ativo = models.BooleanField(default=True)
    e_associacao = models.BooleanField(
        "é a Associação (prédio próprio)", default=False,
        help_text="Consumidora própria: não paga taxa de disponibilidade.",
    )
    valor_mensalidade = models.DecimalField(
        "mensalidade (R$)", max_digits=12, decimal_places=2, default=Decimal("40.00"),
        validators=[MinValueValidator(Decimal("0"))],
    )
    rede_sede = models.BooleanField("rede da Sede", default=False)
    padrao_ligado_sede = models.BooleanField("padrão ligado na Sede", default=False)
    leitura_inicial_sede = models.PositiveIntegerField("leitura inicial do medidor (Sede)", null=True, blank=True)
    rede_poco = models.BooleanField("rede do Poço", default=False)
    padrao_ligado_poco = models.BooleanField("padrão ligado no Poço", default=False)
    leitura_inicial_poco = models.PositiveIntegerField("leitura inicial do medidor (Poço)", null=True, blank=True)
    agua_ligada = models.BooleanField("água ligada", default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rede_sede=False) | models.Q(leitura_inicial_sede__isnull=False),
                name="associado_sede_exige_leitura_inicial",
            ),
            models.CheckConstraint(
                condition=models.Q(rede_poco=False) | models.Q(leitura_inicial_poco__isnull=False),
                name="associado_poco_exige_leitura_inicial",
            ),
            models.CheckConstraint(
                condition=models.Q(valor_mensalidade__gte=0), name="associado_mensalidade_nao_negativa",
            ),
        ]

    def __str__(self):
        return self.nome

    def leitura_inicial(self, rede):
        return self.leitura_inicial_sede if rede == "SEDE" else self.leitura_inicial_poco
