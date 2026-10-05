from decimal import Decimal

from django.db import models
from django.db.models import F, Q

from core.utils import hoje


class TipoCobranca(models.TextChoices):
    ENERGIA = "ENERGIA", "Energia"
    MENSALIDADE = "MENSALIDADE", "Mensalidade"
    AGUA = "AGUA", "Água"
    MULTA = "MULTA", "Multa"


class RedeCobranca(models.TextChoices):
    SEDE = "SEDE", "Sede"
    POCO = "POCO", "Poço"
    # Mensalidade e água usam NENHUMA em vez de nulo: o banco não considera
    # dois nulos iguais e a restrição de unicidade deixaria passar duplicatas.
    NENHUMA = "NENHUMA", "Nenhuma"


class StatusCobranca(models.TextChoices):
    PENDENTE = "PENDENTE", "Pendente"
    PARCIAL = "PARCIAL", "Parcial"
    PAGA = "PAGA", "Paga"


class Cobranca(models.Model):
    """Valor devido por um associado. O valor é copiado na criação e nunca recalculado."""

    associado = models.ForeignKey("associados.Associado", on_delete=models.PROTECT, related_name="cobrancas")
    tipo = models.CharField(max_length=12, choices=TipoCobranca.choices)
    rede = models.CharField(max_length=7, choices=RedeCobranca.choices, default=RedeCobranca.NENHUMA)
    competencia = models.DateField("competência", help_text="Sempre o 1º dia do mês.")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    valor_disponibilidade = models.DecimalField(
        "taxa de disponibilidade incluída", max_digits=12, decimal_places=2, default=Decimal("0.00"),
        help_text="Parte do valor que é taxa de disponibilidade (já somada em valor).",
    )
    valor_pago = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    vencimento = models.DateField(null=True, blank=True, help_text="Vazio para mensalidade e água.")
    status = models.CharField(max_length=8, choices=StatusCobranca.choices, default=StatusCobranca.PENDENTE)
    fechamento = models.ForeignKey(
        "energia.FechamentoEnergia", on_delete=models.PROTECT, null=True, blank=True, related_name="cobrancas",
        help_text="Origem: fechamento de energia que gerou a cobrança.",
    )
    consumo_kwh = models.PositiveIntegerField(null=True, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-competencia", "tipo", "associado__nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["associado", "tipo", "competencia", "rede"], name="cobranca_unica",
            ),
            models.CheckConstraint(condition=Q(valor__gte=0), name="cobranca_valor_nao_negativo"),
            models.CheckConstraint(condition=Q(valor_pago__gte=0), name="cobranca_valor_pago_nao_negativo"),
            models.CheckConstraint(condition=Q(valor_pago__lte=F("valor")), name="cobranca_pago_ate_o_valor"),
            models.CheckConstraint(
                condition=Q(valor_disponibilidade__gte=0) & Q(valor_disponibilidade__lte=F("valor")),
                name="cobranca_disponibilidade_dentro_do_valor",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo__in=["MENSALIDADE", "AGUA"], rede="NENHUMA")
                    | (Q(tipo__in=["ENERGIA", "MULTA"]) & ~Q(rede="NENHUMA"))
                ),
                name="cobranca_rede_coerente_com_tipo",
            ),
        ]

    def __str__(self):
        return f"{self.rotulo_tipo} {self.competencia:%m/%Y} — {self.associado}"

    @property
    def rotulo_tipo(self):
        if self.rede == RedeCobranca.NENHUMA:
            return self.get_tipo_display()
        return f"{self.get_tipo_display()} ({self.get_rede_display()})"

    @property
    def saldo(self):
        return max(self.valor - self.valor_pago, Decimal("0.00"))

    @property
    def em_aberto(self):
        return self.status != StatusCobranca.PAGA

    @property
    def em_atraso(self):
        """Calculado, nunca gravado: tem vencimento, já passou e ainda há saldo."""
        return bool(self.vencimento and self.vencimento < hoje() and self.saldo > 0)

    def atualizar_status(self):
        if self.valor_pago >= self.valor:
            self.status = StatusCobranca.PAGA
        elif self.valor_pago > 0:
            self.status = StatusCobranca.PARCIAL
        else:
            self.status = StatusCobranca.PENDENTE


class Pagamento(models.Model):
    cobranca = models.ForeignKey(Cobranca, on_delete=models.PROTECT, related_name="pagamentos")
    valor = models.DecimalField(max_digits=12, decimal_places=2, help_text="Valor recebido, inclusive excedente.")
    data = models.DateField("data do pagamento")
    observacao = models.CharField("observação", max_length=200, blank=True)
    lote = models.UUIDField(null=True, blank=True, help_text="Identifica pagamentos da mesma baixa em lote.")
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "-pk"]
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="pagamento_valor_positivo")]

    def __str__(self):
        return f"{self.valor} em {self.data:%d/%m/%Y}"


class MovimentoCredito(models.Model):
    """Crédito gerado pelo excedente de um pagamento. Saldo de crédito é a soma dos movimentos."""

    associado = models.ForeignKey("associados.Associado", on_delete=models.PROTECT, related_name="creditos")
    valor = models.DecimalField(max_digits=12, decimal_places=2)
    pagamento = models.ForeignKey(Pagamento, on_delete=models.PROTECT, null=True, blank=True, related_name="creditos")
    data = models.DateField()
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimento de crédito"
        verbose_name_plural = "movimentos de crédito"
        constraints = [models.CheckConstraint(condition=Q(valor__gt=0), name="credito_valor_positivo")]
