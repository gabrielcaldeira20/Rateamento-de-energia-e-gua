from django.db import models
from django.db.models import F, Q


class Rede(models.TextChoices):
    SEDE = "SEDE", "Sede"
    POCO = "POCO", "Poço"


class FechamentoEnergia(models.Model):
    """Fechamento mensal de uma rede: a conta da concessionária e o fator de rateio."""

    rede = models.CharField(max_length=4, choices=Rede.choices)
    competencia = models.DateField("competência", help_text="Sempre o 1º dia do mês.")
    valor_total = models.DecimalField("valor total da conta (R$)", max_digits=12, decimal_places=2)
    kwh_total = models.PositiveIntegerField("kWh total da conta")
    fator = models.DecimalField("fator (R$/kWh)", max_digits=12, decimal_places=6)
    vencimento = models.DateField()
    perda_kwh = models.IntegerField("perda (kWh)", help_text="kWh da conta menos a soma dos consumos.")
    perda_valor = models.DecimalField("perda (R$)", max_digits=12, decimal_places=2)
    fechado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-competencia", "rede"]
        verbose_name = "fechamento de energia"
        verbose_name_plural = "fechamentos de energia"
        constraints = [
            models.UniqueConstraint(fields=["rede", "competencia"], name="fechamento_unico_rede_competencia"),
            models.CheckConstraint(condition=Q(kwh_total__gt=0), name="fechamento_kwh_positivo"),
            models.CheckConstraint(condition=Q(valor_total__gt=0), name="fechamento_valor_positivo"),
        ]

    def __str__(self):
        return f"{self.get_rede_display()} {self.competencia:%m/%Y}"


class Leitura(models.Model):
    fechamento = models.ForeignKey(FechamentoEnergia, on_delete=models.PROTECT, related_name="leituras")
    associado = models.ForeignKey("associados.Associado", on_delete=models.PROTECT, related_name="leituras")
    leitura_anterior = models.PositiveIntegerField()
    leitura_atual = models.PositiveIntegerField()
    consumo_kwh = models.PositiveIntegerField()
    valor_energia = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["fechamento", "associado"], name="leitura_unica_por_fechamento"),
            models.CheckConstraint(
                condition=Q(leitura_atual__gte=F("leitura_anterior")), name="leitura_atual_nao_menor_que_anterior",
            ),
        ]

    def __str__(self):
        return f"{self.associado} — {self.fechamento}"
