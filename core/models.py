from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Configuracao(models.Model):
    """Configuração da associação. Existe uma única linha (pk=1).

    Os valores são copiados para as cobranças no momento da criação,
    então alterar aqui só afeta cobranças futuras.
    """

    nome_associacao = models.CharField("nome da associação", max_length=120, default="Associação Alfa Serra Velha")
    chave_pix = models.CharField("chave PIX", max_length=140, blank=True)
    taxa_disponibilidade = models.DecimalField(
        "taxa de disponibilidade (R$ por rede)", max_digits=12, decimal_places=2,
        default=Decimal("5.00"), validators=[MinValueValidator(Decimal("0"))],
    )
    valor_agua = models.DecimalField(
        "valor da água (R$)", max_digits=12, decimal_places=2,
        default=Decimal("35.00"), validators=[MinValueValidator(Decimal("0"))],
    )
    limite_kwh_multa = models.PositiveIntegerField("limite de kWh para multa", default=100)
    percentual_multa = models.DecimalField(
        "percentual da multa (%)", max_digits=5, decimal_places=2, default=Decimal("10.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    class Meta:
        verbose_name = "configuração"
        verbose_name_plural = "configuração"
        constraints = [
            models.CheckConstraint(condition=models.Q(pk=1), name="configuracao_linha_unica"),
        ]

    def __str__(self):
        return self.nome_associacao

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def atual(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
