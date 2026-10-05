"""Exportação do relatório financeiro em CSV e PDF.

Os números vêm das mesmas funções de services.py que a tela usa
(resumo_periodo, pagamentos_do_periodo, despesas_do_periodo), então nunca divergem.
"""
import csv
import io
from dataclasses import dataclass

from django.utils import timezone

from core.models import Configuracao
from core.utils import formatar_brl, mes_label, mes_iso

from . import services


@dataclass
class DadosExportacao:
    associacao: str
    regime: str
    rotulo_regime: str
    inicio: object
    fim: object
    gerado_em: object
    resumo: services.Resumo
    entradas: list
    despesas: list

    @property
    def periodo(self):
        return f"{mes_label(self.inicio)} a {mes_label(self.fim)}"

    @property
    def nome_arquivo(self):
        return f"relatorio-financeiro-{self.regime}-{mes_iso(self.inicio)}_{mes_iso(self.fim)}"


def montar(inicio, fim, regime):
    return DadosExportacao(
        associacao=Configuracao.atual().nome_associacao,
        regime=regime,
        rotulo_regime=dict(services.MODOS)[regime],
        inicio=inicio,
        fim=fim,
        gerado_em=timezone.localtime(),
        resumo=services.resumo_periodo(inicio, fim, regime),
        entradas=list(services.pagamentos_do_periodo(inicio, fim, regime).order_by("data", "pk")),
        despesas=list(services.despesas_do_periodo(inicio, fim, regime).order_by("data", "pk")),
    )


def valor(v):
    """Decimal no formato brasileiro, sem símbolo: 1.234,56."""
    return formatar_brl(v, simbolo=False)


def linhas_resumo(d):
    return [
        ("Entradas", d.resumo.entradas),
        ("Despesas", d.resumo.despesas),
        ("Saldo", d.resumo.saldo),
        ("Taxa de disponibilidade", d.resumo.disponibilidade),
    ]


def linhas_entradas(d):
    return [
        (p.data.strftime("%d/%m/%Y"), p.cobranca.associado.nome, p.cobranca.rotulo_tipo,
         mes_label(p.cobranca.competencia), p.valor)
        for p in d.entradas
    ]


def linhas_despesas(d):
    return [
        (x.data.strftime("%d/%m/%Y"), mes_label(x.competencia), x.rotulo_categoria, x.descricao, x.valor)
        for x in d.despesas
    ]


# ---------------------------------------------------------------- CSV

def gerar_csv(d):
    """CSV em UTF-8 com BOM e separador ponto e vírgula, para abrir direto no Excel em português."""
    saida = io.StringIO()
    w = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    w.writerow(["Relatório Financeiro"])
    w.writerow(["Associação", d.associacao])
    w.writerow(["Regime", d.rotulo_regime])
    w.writerow(["Período", d.periodo])
    w.writerow(["Gerado em", d.gerado_em.strftime("%d/%m/%Y %H:%M")])
    w.writerow([])
    w.writerow(["Resumo"])
    for rotulo, v in linhas_resumo(d):
        w.writerow([rotulo, valor(v)])
    w.writerow([])
    w.writerow(["Detalhamento das entradas"])
    w.writerow(["Data", "Associado", "Tipo", "Competência", "Valor (R$)"])
    for *campos, v in linhas_entradas(d):
        w.writerow([*campos, valor(v)])
    w.writerow(["Total de entradas", "", "", "", valor(d.resumo.entradas)])
    w.writerow([])
    w.writerow(["Detalhamento das despesas"])
    w.writerow(["Data", "Competência", "Categoria", "Descrição", "Valor (R$)"])
    for *campos, v in linhas_despesas(d):
        w.writerow([*campos, valor(v)])
    w.writerow(["Total de despesas", "", "", "", valor(d.resumo.despesas)])
    return ("﻿" + saida.getvalue()).encode("utf-8")


# ---------------------------------------------------------------- PDF

def gerar_pdf(d):
    """PDF com título, associação, regime, período, data de geração, resumo e tabelas."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"Relatório Financeiro — {d.periodo}", author=d.associacao, pageCompression=0,
    )
    estilos = getSampleStyleSheet()
    pequeno = estilos["BodyText"].clone("pequeno", fontSize=8, leading=10)
    verde = colors.HexColor("#4a5d3a")

    def tabela(cabecalho, linhas, larguras, total=None):
        dados = [cabecalho] + [[Paragraph(str(c), pequeno) for c in linha[:-1]] + [valor(linha[-1])] for linha in linhas]
        if not linhas:
            dados.append(["Nenhum registro no período."] + [""] * (len(cabecalho) - 1))
        if total is not None:
            dados.append(["Total"] + [""] * (len(cabecalho) - 2) + [valor(total)])
        t = Table(dados, colWidths=larguras, repeatRows=1)
        estilo = [
            ("BACKGROUND", (0, 0), (-1, 0), verde),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d0bf")),
        ]
        if total is not None:
            estilo.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
        t.setStyle(TableStyle(estilo))
        return t

    largura = A4[0] - doc.leftMargin - doc.rightMargin
    historia = [
        Paragraph("Relatório Financeiro", estilos["Title"]),
        Paragraph(d.associacao, estilos["Heading3"]),
        Paragraph(
            f"Regime: {d.rotulo_regime}<br/>Período: {d.periodo}<br/>"
            f"Gerado em: {d.gerado_em.strftime('%d/%m/%Y %H:%M')}",
            estilos["BodyText"],
        ),
        Spacer(1, 0.4 * cm),
        Paragraph("Resumo", estilos["Heading2"]),
    ]
    resumo = Table([[r, valor(v)] for r, v in linhas_resumo(d)], colWidths=[largura * 0.6, largura * 0.4])
    resumo.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#d8d0bf")),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
    ]))
    historia += [
        resumo,
        Paragraph("Valores em reais (R$).", pequeno),
        Spacer(1, 0.4 * cm),
        Paragraph("Entradas", estilos["Heading2"]),
        tabela(["Data", "Associado", "Tipo", "Competência", "Valor"], linhas_entradas(d),
               [largura * f for f in (0.13, 0.37, 0.2, 0.14, 0.16)], d.resumo.entradas),
        Spacer(1, 0.4 * cm),
        Paragraph("Despesas", estilos["Heading2"]),
        tabela(["Data", "Competência", "Categoria", "Descrição", "Valor"], linhas_despesas(d),
               [largura * f for f in (0.13, 0.14, 0.2, 0.37, 0.16)], d.resumo.despesas),
    ]

    def rodape(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, 0.9 * cm, f"{d.associacao} · Relatório Financeiro · {d.periodo}")
        canvas.drawRightString(A4[0] - doc.rightMargin, 0.9 * cm, f"Página {documento.page}")
        canvas.restoreState()

    doc.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
