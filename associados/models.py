from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Associado(models.Model):
    """Cadastro do associado. Guarda só o estado atual, sem histórico por data."""

    nome = models.CharField(max_length=150)
    cpf_cnpj = models.CharField(
        "CPF/CNPJ", max_length=18, null=True, blank=True, unique=True,
        help_text="Opcional. Vazio é gravado como nulo, para não colidir na restrição de único.",
    )
    contato = models.CharField(
        "contato/WhatsApp", max_length=40, blank=True,
        help_text="Opcional. Sem telefone, o associado não recebe lembrete pelo WhatsApp.",
    )
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

    def save(self, *args, **kwargs):
        # String vazia colidiria na restrição unique; documento ausente é sempre nulo.
        if not (self.cpf_cnpj or "").strip():
            self.cpf_cnpj = None
        super().save(*args, **kwargs)

    def leitura_inicial(self, rede):
        return self.leitura_inicial_sede if rede == "SEDE" else self.leitura_inicial_poco


class TipoLigacao(models.TextChoices):
    SEDE = "SEDE", "Rede da Sede"
    POCO = "POCO", "Rede do Poço"
    AGUA = "AGUA", "Água"


# Campo do Associado que reflete cada tipo de ligação.
CAMPO_DO_TIPO = {
    TipoLigacao.SEDE: "rede_sede",
    TipoLigacao.POCO: "rede_poco",
    TipoLigacao.AGUA: "agua_ligada",
}


class HistoricoLigacao(models.Model):
    """Mudança de estado de um serviço do associado em uma data.

    Os campos rede_sede, rede_poco e agua_ligada do Associado refletem o registro
    mais recente por data de cada tipo.
    """

    associado = models.ForeignKey(Associado, on_delete=models.CASCADE, related_name="historico_ligacoes")
    tipo = models.CharField(max_length=4, choices=TipoLigacao.choices)
    ligado = models.BooleanField(help_text="Novo estado a partir desta data.")
    data = models.DateField()
    observacao = models.CharField("observação", max_length=200, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-data", "tipo", "-pk"]
        verbose_name = "histórico de ligação"
        verbose_name_plural = "histórico de ligações"
        constraints = [
            models.UniqueConstraint(fields=["associado", "tipo", "data"], name="historico_unico_por_dia"),
        ]

    def __str__(self):
        estado = "ligado" if self.ligado else "desligado"
        return f"{self.associado} — {self.get_tipo_display()} {estado} em {self.data:%d/%m/%Y}"
