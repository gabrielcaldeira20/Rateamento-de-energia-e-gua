"""Carga inicial de associados a partir de um CSV exportado das planilhas atuais.

Uso: python manage.py importar_planilhas associados.csv [--simular]

Colunas aceitas (cabeçalho obrigatório, separador ; ou ,):
  nome, contato, endereco, mensalidade, agua, e_associacao,
  rede_sede, padrao_sede, leitura_sede, rede_poco, padrao_poco, leitura_poco
Campos sim/não aceitam: sim, s, x, 1, true (qualquer outro valor é não).
Associados com o mesmo nome de um já cadastrado são ignorados, então rodar duas vezes não duplica.
Tudo roda em uma transação: se uma linha tiver erro, nada é gravado.
"""
import csv
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from associados.forms import AssociadoForm
from associados.models import Associado

VERDADEIROS = {"sim", "s", "x", "1", "true", "verdadeiro", "ligada", "ligado"}


def booleano(valor):
    return (valor or "").strip().lower() in VERDADEIROS


def inteiro(valor):
    """Leitura de medidor: só os dígitos ("1.234" vira 1234). A parte após a vírgula é descartada."""
    texto = (valor or "").split(",")[0]
    return re.sub(r"\D", "", texto)


def decimal_br(valor, padrao=""):
    texto = (valor or "").strip().replace("R$", "").replace(" ", "")
    if not texto:
        return padrao
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return str(Decimal(texto))
    except InvalidOperation:
        return texto  # o formulário aponta o erro


class Command(BaseCommand):
    help = "Importa associados e leituras iniciais de um CSV."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument("--simular", action="store_true", help="Valida tudo sem gravar.")

    def handle(self, *args, **opcoes):
        caminho = Path(opcoes["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        texto = caminho.read_text(encoding="utf-8-sig")
        separador = ";" if texto.splitlines()[0].count(";") >= texto.splitlines()[0].count(",") else ","
        linhas = list(csv.DictReader(texto.splitlines(), delimiter=separador))
        existentes = {n.strip().lower() for n in Associado.objects.values_list("nome", flat=True)}
        criados, ignorados, erros = 0, 0, []

        with transaction.atomic():
            for numero, linha in enumerate(linhas, start=2):
                linha = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items()}
                nome = linha.get("nome", "")
                if not nome:
                    continue
                if nome.lower() in existentes:
                    ignorados += 1
                    continue
                dados = {
                    "nome": nome,
                    "contato": linha.get("contato", ""),
                    "endereco": linha.get("endereco", ""),
                    "valor_mensalidade": decimal_br(linha.get("mensalidade"), "0"),
                    "leitura_inicial_sede": inteiro(linha.get("leitura_sede")),
                    "leitura_inicial_poco": inteiro(linha.get("leitura_poco")),
                }
                for campo, coluna in (
                    ("agua_ligada", "agua"), ("e_associacao", "e_associacao"),
                    ("rede_sede", "rede_sede"), ("padrao_ligado_sede", "padrao_sede"),
                    ("rede_poco", "rede_poco"), ("padrao_ligado_poco", "padrao_poco"),
                ):
                    if booleano(linha.get(coluna)):
                        dados[campo] = "on"
                form = AssociadoForm(data=dados)
                if not form.is_valid():
                    detalhes = "; ".join(f"{c}: {' '.join(e)}" for c, e in form.errors.items())
                    erros.append(f"Linha {numero} ({nome}): {detalhes}")
                    continue
                form.save()
                existentes.add(nome.lower())
                criados += 1

            if erros:
                transaction.set_rollback(True)
                for erro in erros:
                    self.stderr.write(erro)
                raise CommandError(f"{len(erros)} linha(s) com erro. Nada foi gravado.")
            if opcoes["simular"]:
                transaction.set_rollback(True)

        prefixo = "Simulação: seriam criados" if opcoes["simular"] else "Criados"
        self.stdout.write(self.style.SUCCESS(f"{prefixo} {criados} associado(s). {ignorados} já existiam e foram ignorados."))
