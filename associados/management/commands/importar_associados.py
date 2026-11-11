"""Importa os associados da planilha oficial da associação (CSV).

Uso (rode sempre primeiro com --simular):
  python manage.py importar_associados associados-para-importar.csv --data-inicio 2026-12-01 --simular
  python manage.py importar_associados associados-para-importar.csv --data-inicio 2026-12-01

--data-inicio é obrigatória e precisa ser o primeiro dia de um mês: é a virada do sistema.
Ela vira a data dos registros do histórico de ligação (água e, quando informadas, as redes),
que é o que a cobrança e o rateio consultam.

Colunas obrigatórias no cabeçalho (separador , ou ;):
  nome, cpf_cnpj, telefone, numero_padrao, sede, poco, padrao_ligado, agua, valor_agua,
  mensalidade, leitura_sede, leitura_poco, ativo
Opcionais: endereco, isento_disponibilidade, observacao. A antiga coluna energia é ignorada:
a fonte da verdade da rede é a folha de leitura dos padrões (sede, poco, numero_padrao).

Célula vazia é ausência de informação, não "não": o campo correspondente não é alterado.

Rede sem leitura inicial não é ligada. Sem leitura, o primeiro fechamento usaria 0 como
leitura anterior e cobraria o relógio inteiro como consumo. A linha não é rejeitada: a rede,
o padrao_ligado e o histórico de energia ficam de fora, com aviso, até a planilha trazer a
leitura. Rodar de novo, com a leitura, liga a rede na --data-inicio.

Não duplica: procura pelo CPF/CNPJ, depois pelo numero_padrao e, sem nenhum dos dois, pelo
nome entre os associados que também não têm documento nem padrão.
Tudo roda em uma transação: se uma linha tiver erro, nada é gravado.

Não importa (o sistema ainda não tem onde guardar ou não usa):
  isento_disponibilidade, observacao e o valor_agua por pessoa. Diferenças aparecem como
  aviso no resumo.
"""
import csv
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from associados.models import Associado, HistoricoLigacao, TipoLigacao
from associados.services import recalcular_estado, registrar_mudanca, situacao_em
from core.models import Configuracao

OBRIGATORIAS = [
    "nome", "cpf_cnpj", "telefone", "numero_padrao", "sede", "poco", "padrao_ligado",
    "agua", "valor_agua", "mensalidade", "leitura_sede", "leitura_poco", "ativo",
]
VERDADEIROS = {"sim", "s", "true", "1"}
FALSOS = {"nao", "não", "n", "false", "0"}
REDES = (("SEDE", "sede", "Sede"), ("POCO", "poco", "Poço"))


# ---------------------------------------------------------------- conversões

def booleano(valor, coluna):
    """sim/não. Vazio vira None: ausência de informação, não falso."""
    texto = valor.strip().lower()
    if not texto:
        return None
    if texto in VERDADEIROS:
        return True
    if texto in FALSOS:
        return False
    raise ValueError(f"{coluna}: '{valor}' não é sim ou não")


def inteiro(valor, coluna):
    """Leitura de medidor: inteiro não negativo. Vazio vira None; zero é leitura válida."""
    texto = valor.strip()
    if not texto:
        return None
    if not re.fullmatch(r"-?\d+", texto):
        raise ValueError(f"{coluna}: '{valor}' não é um número inteiro")
    numero = int(texto)
    if numero < 0:
        raise ValueError(f"{coluna}: não pode ser negativo")
    return numero


def dinheiro(valor, coluna):
    """Valor em reais: aceita 35, 35.00 e 35,00. Vazio vira None."""
    texto = valor.strip().replace("R$", "").strip()
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        raise ValueError(f"{coluna}: '{valor}' não é um valor")
    if numero < 0:
        raise ValueError(f"{coluna}: não pode ser negativo")
    return numero


def _digito(digitos, pesos):
    resto = sum(int(d) * p for d, p in zip(digitos, pesos)) % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf_valido(d):
    if len(d) != 11 or d == d[0] * 11:
        return False
    dv1 = _digito(d[:9], range(10, 1, -1))
    dv2 = _digito(d[:9] + dv1, range(11, 1, -1))
    return d[9:] == dv1 + dv2


def cnpj_valido(d):
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _digito(d[:12], pesos1)
    dv2 = _digito(d[:12] + dv1, [6] + pesos1)
    return d[12:] == dv1 + dv2


def documento(valor):
    """Devolve (documento formatado ou None, aviso ou None). Nunca rejeita a linha."""
    texto = valor.strip()
    if not texto:
        return None, None
    d = re.sub(r"\D", "", texto)
    if len(d) == 11:
        formatado = f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        return formatado, None if cpf_valido(d) else f"CPF {formatado} com dígito verificador inválido"
    if len(d) == 14:
        formatado = f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
        return formatado, None if cnpj_valido(d) else f"CNPJ {formatado} com dígito verificador inválido"
    return texto, f"CPF/CNPJ '{texto}' não tem 11 nem 14 dígitos"


def ler_csv(caminho):
    texto = caminho.read_text(encoding="utf-8-sig")
    linhas = texto.splitlines()
    if not linhas:
        raise CommandError("O arquivo está vazio.")
    separador = ";" if linhas[0].count(";") > linhas[0].count(",") else ","
    leitor = csv.DictReader(linhas, delimiter=separador)
    colunas = [(c or "").strip().lower() for c in leitor.fieldnames or []]
    faltando = [c for c in OBRIGATORIAS if c not in colunas]
    if faltando:
        raise CommandError(f"Colunas obrigatórias ausentes no cabeçalho: {', '.join(faltando)}")
    registros = []
    for numero, linha in enumerate(leitor, start=2):
        linha = {(k or "").strip().lower(): (v or "").strip() for k, v in linha.items() if k}
        if any(linha.values()):
            registros.append((numero, linha))
    return colunas, registros


# ---------------------------------------------------------------- comando

class Command(BaseCommand):
    help = "Importa os associados da planilha oficial (use --simular na primeira vez)."

    def add_arguments(self, parser):
        parser.add_argument("arquivo")
        parser.add_argument(
            "--data-inicio",
            help="Início do sistema, AAAA-MM-DD, sempre o dia 1 do mês. Obrigatória, sem valor padrão.",
        )
        parser.add_argument("--simular", action="store_true", help="Lê, valida e mostra o que faria, sem gravar.")

    def handle(self, *args, **opcoes):
        data = self.data_inicio(opcoes["data_inicio"])
        simular = opcoes["simular"]
        caminho = Path(opcoes["arquivo"])
        if not caminho.exists():
            raise CommandError(f"Arquivo não encontrado: {caminho}")
        colunas, registros = ler_csv(caminho)
        self.valor_agua_padrao = Configuracao.atual().valor_agua
        self.avisos = []

        validos, erros = self.validar(registros, colunas)
        rejeitadas = {numero for numero, _ in erros}

        criados = atualizados = 0
        with transaction.atomic():
            for numero, dados in validos:
                try:
                    with transaction.atomic():
                        novo = self.gravar(numero, dados, data)
                except ValidationError as erro:
                    erros.append((numero, f"Linha {numero} ({dados['nome']}): {'; '.join(erro.messages)}"))
                    rejeitadas.add(numero)
                    continue
                criados += novo
                atualizados += not novo
                self.stdout.write(f"Linha {numero}: {'criar' if novo else 'atualizar'} {self.descrever(dados)}")
            if erros or simular:
                transaction.set_rollback(True)

        self.resumo(simular, data, colunas, registros, criados, atualizados, len(rejeitadas), sorted(erros))
        if erros:
            raise CommandError(f"{len(rejeitadas)} linha(s) rejeitada(s). Nada foi gravado.")

    def data_inicio(self, valor):
        if not valor:
            raise CommandError(
                "Informe o início do sistema com --data-inicio AAAA-MM-DD (o dia 1 do mês em que "
                "o sistema entra em operação). Não há valor padrão, de propósito."
            )
        try:
            data = date.fromisoformat(valor)
        except ValueError:
            raise CommandError(f"Data inválida: {valor}. Use o formato AAAA-MM-DD.")
        if data.day != 1:
            raise CommandError(
                f"--data-inicio precisa ser o primeiro dia do mês (recebi {data:%d/%m/%Y}), "
                "para o primeiro mês de cobrança sair inteiro."
            )
        return data

    def avisar(self, numero, nome, texto):
        self.avisos.append((numero, f"Linha {numero} ({nome or 'sem nome'}): {texto}"))

    # ------------------------------------------------------------ validação

    def validar(self, registros, colunas):
        """Converte e confere cada linha antes de gravar qualquer coisa."""
        validos, erros = [], []
        documentos, nomes_sem_doc, padroes = {}, {}, {}
        for numero, linha in registros:
            nome = re.sub(r"\s+", " ", linha.get("nome", ""))
            problemas = []
            cpf, aviso_cpf = documento(linha.get("cpf_cnpj", ""))
            dados = {
                "nome": nome,
                "cpf_cnpj": cpf,
                "contato": re.sub(r"\D", "", linha.get("telefone", "")),
                "endereco": linha.get("endereco", ""),
            }
            if not nome:
                problemas.append("nome vazio")
            if aviso_cpf:
                self.avisar(numero, nome, aviso_cpf)
            if cpf and len(cpf) > 18:
                problemas.append(f"cpf_cnpj '{cpf}' tem mais de 18 caracteres")
            if cpf:
                if cpf in documentos:
                    problemas.append(f"CPF/CNPJ repetido (já aparece na linha {documentos[cpf]})")
                else:
                    documentos[cpf] = numero
            conversoes = [
                ("ativo", booleano), ("agua", booleano), ("sede", booleano), ("poco", booleano),
                ("padrao_ligado", booleano), ("numero_padrao", inteiro),
                ("leitura_sede", inteiro), ("leitura_poco", inteiro),
                ("valor_agua", dinheiro), ("mensalidade", dinheiro),
            ]
            for coluna, converter in conversoes:
                try:
                    dados[coluna] = converter(linha.get(coluna, ""), coluna)
                except ValueError as erro:
                    problemas.append(str(erro))
            if "isento_disponibilidade" in colunas:
                try:
                    dados["isento_disponibilidade"] = booleano(linha.get("isento_disponibilidade", ""), "isento_disponibilidade")
                except ValueError as erro:
                    problemas.append(str(erro))
            dados["observacao"] = linha.get("observacao", "")

            padrao = dados.get("numero_padrao")
            if padrao is not None:
                if padrao == 0 or padrao > 32767:
                    problemas.append(f"numero_padrao {padrao} fora do intervalo (1 a 32767)")
                elif padrao in padroes:
                    problemas.append(f"numero_padrao {padrao} repetido (já aparece na linha {padroes[padrao]})")
                else:
                    padroes[padrao] = numero
            if not cpf and padrao is None and nome:
                chave = nome.lower()
                if chave in nomes_sem_doc:
                    problemas.append(
                        f"nome repetido sem CPF/CNPJ nem numero_padrao (já aparece na linha {nomes_sem_doc[chave]}); "
                        "nesse caso o nome é a única forma de não duplicar"
                    )
                else:
                    nomes_sem_doc[chave] = numero

            if not problemas:
                if dados["mensalidade"] is None:
                    problemas.append("mensalidade vazia")
                for _, rede, rotulo in REDES:
                    ligado, leitura = dados[rede], dados[f"leitura_{rede}"]
                    dados[f"pendente_{rede}"] = bool(ligado and leitura is None)
                    if dados[f"pendente_{rede}"]:
                        estado = {True: "ligado", False: "desligado", None: "não informado"}[dados["padrao_ligado"]]
                        self.avisar(numero, nome,
                                    f"rede {rotulo} informada sem leitura_{rede}: não ligada nesta importação "
                                    f"(padrão {estado}); rode de novo quando a leitura chegar")
                    elif ligado and dados["padrao_ligado"] is None:
                        problemas.append(f"{rede} = sim com leitura, mas padrao_ligado vazio")
                    elif ligado is False and leitura is not None:
                        problemas.append(f"leitura_{rede} preenchida, mas {rede} = não")
                    elif ligado is None and leitura is not None:
                        problemas.append(f"leitura_{rede} preenchida, mas {rede} está vazio")
                tem_rede = dados["sede"] or dados["poco"]
                if dados["sede"] and dados["poco"]:
                    self.avisar(numero, nome, "sede e poco = sim: o cadastro guarda um único numero_padrao por associado")
                if padrao is not None and not tem_rede:
                    self.avisar(numero, nome, f"numero_padrao {padrao} sem rede informada")
                if tem_rede and padrao is None:
                    self.avisar(numero, nome, "rede informada sem numero_padrao")
                if dados["padrao_ligado"] is not None and not tem_rede:
                    self.avisar(numero, nome, "padrao_ligado preenchido sem rede informada")
                self.avisos_de_valores(numero, dados)

            if problemas:
                erros.append((numero, f"Linha {numero} ({nome or 'sem nome'}): {'; '.join(problemas)}"))
            else:
                validos.append((numero, dados))
        return validos, erros

    def avisos_de_valores(self, numero, dados):
        """O que a planilha traz e o sistema ainda não guarda: só avisa, não rejeita."""
        nome, valor = dados["nome"], dados["valor_agua"]
        if dados["agua"] and valor is not None and valor != self.valor_agua_padrao:
            self.avisar(numero, nome,
                        f"valor_agua R$ {valor} difere do valor único da Configuração (R$ {self.valor_agua_padrao}); "
                        "a cobrança sairá com o valor da Configuração")
        if dados["agua"] is False and valor:
            self.avisar(numero, nome, f"agua = não, mas valor_agua = R$ {valor}")
        if dados.get("isento_disponibilidade"):
            self.avisar(numero, nome, "isento_disponibilidade = sim não é importado: o sistema ainda não tem esse campo")
        if dados["observacao"]:
            self.avisar(numero, nome, "observação descartada: o cadastro não tem campo de observação")

    # ------------------------------------------------------------ gravação

    def localizar(self, dados):
        """Por CPF/CNPJ, depois por numero_padrao; sem nenhum dos dois, pelo nome."""
        cpf, padrao = dados["cpf_cnpj"], dados["numero_padrao"]
        if cpf:
            existente = Associado.objects.filter(cpf_cnpj=cpf).first()
            if existente:
                return existente
        if padrao is not None:
            existente = Associado.objects.filter(numero_padrao=padrao).first()
            if existente:
                if cpf and existente.cpf_cnpj and existente.cpf_cnpj != cpf:
                    raise ValidationError(
                        f"o padrão {padrao} já é de {existente.nome}, com outro CPF/CNPJ ({existente.cpf_cnpj})"
                    )
                return existente
        sem_chave = Associado.objects.filter(
            nome__iexact=dados["nome"], cpf_cnpj__isnull=True, numero_padrao__isnull=True,
        )
        if cpf or padrao is not None:
            if sem_chave.exists():
                raise ValidationError(
                    "já existe associado com este nome e sem CPF/CNPJ nem numero_padrao; para não duplicar "
                    "nem casar pelo nome, cadastre o documento ou o padrão nele pelo sistema e rode de novo"
                )
            return None
        existentes = list(sem_chave)
        if len(existentes) > 1:
            raise ValidationError(f"há {len(existentes)} associados sem CPF/CNPJ com este nome; acerte pelo sistema")
        return existentes[0] if existentes else None

    def gravar(self, numero, dados, data):
        """Cria ou atualiza o associado. Coluna vazia não altera o campo."""
        existente = self.localizar(dados)
        novo = existente is None
        associado = existente or Associado()

        associado.nome = dados["nome"]
        if dados["cpf_cnpj"]:
            associado.cpf_cnpj = dados["cpf_cnpj"]
        if dados["numero_padrao"] is not None:
            associado.numero_padrao = dados["numero_padrao"]
        if dados["contato"] or novo:
            associado.contato = dados["contato"]
        if dados["endereco"] or novo:
            associado.endereco = dados["endereco"]
        if dados["ativo"] is not None:
            associado.ativo = dados["ativo"]
        associado.valor_mensalidade = dados["mensalidade"]
        for _, rede, _ in REDES:
            ligado = dados[rede]
            if ligado is None or dados[f"pendente_{rede}"]:
                continue  # rede não informada, ou informada sem leitura: não mexe
            setattr(associado, f"rede_{rede}", ligado)
            setattr(associado, f"padrao_ligado_{rede}", bool(ligado and dados["padrao_ligado"]))
            if ligado:
                setattr(associado, f"leitura_inicial_{rede}", dados[f"leitura_{rede}"])
        associado.full_clean()
        associado.save()

        observacao = f"Início do sistema em {data:%d/%m/%Y} (importação)"
        # Redes: só as informadas com leitura (ou desligadas), e só o que muda na data.
        for tipo, rede, _ in REDES:
            ligado = dados[rede]
            if ligado is None or dados[f"pendente_{rede}"]:
                continue
            if situacao_em(associado, tipo, data) != ligado:
                registrar_mudanca(associado, tipo, ligado, data, observacao)
        # Água: um registro para quem tem água, e nunca um segundo.
        if dados["agua"]:
            if not HistoricoLigacao.objects.filter(associado=associado, tipo=TipoLigacao.AGUA).exists():
                registrar_mudanca(associado, TipoLigacao.AGUA, True, data, observacao)
        elif dados["agua"] is False and associado.agua_ligada:
            self.avisar(numero, dados["nome"],
                        "agua = não, mas a água está ligada no sistema; não alterei, desligue pelo histórico se for o caso")
        recalcular_estado(associado)
        return novo

    def descrever(self, dados):
        partes = []
        if dados["numero_padrao"] is not None:
            partes.append(f"padrão {dados['numero_padrao']}")
        for _, rede, rotulo in REDES:
            if dados[rede] and dados[f"pendente_{rede}"]:
                partes.append(f"{rotulo} aguardando leitura")
            elif dados[rede]:
                partes.append(f"{rotulo} (leitura {dados[f'leitura_{rede}']})")
        if not (dados["sede"] or dados["poco"]):
            partes.append("sem rede")
        if dados["agua"]:
            partes.append("água")
        partes.append(f"mensalidade R$ {dados['mensalidade']}")
        if not dados["cpf_cnpj"]:
            partes.append("sem CPF/CNPJ")
        if not dados["contato"]:
            partes.append("sem telefone")
        if dados["ativo"] is False:
            partes.append("inativo")
        return f"{dados['nome']} — {', '.join(partes)}"

    # ------------------------------------------------------------ resumo

    def resumo(self, simular, data, colunas, registros, criados, atualizados, rejeitadas, erros):
        def vazio(linha, coluna):
            return not linha.get(coluna, "").strip()

        def sim(linha, coluna):
            return linha.get(coluna, "").strip().lower() in VERDADEIROS

        def nao(linha, coluna):
            return linha.get(coluna, "").strip().lower() in FALSOS

        linhas = [linha for _, linha in registros]
        sem_cpf = sum(vazio(l, "cpf_cnpj") for l in linhas)
        sem_tel = sum(not re.sub(r"\D", "", l.get("telefone", "")) for l in linhas)
        sem_padrao = sum(vazio(l, "numero_padrao") for l in linhas)
        na_sede = sum(sim(l, "sede") for l in linhas)
        no_poco = sum(sim(l, "poco") for l in linhas)
        com_rede = sum(sim(l, "sede") or sim(l, "poco") for l in linhas)
        padrao_desligado = sum(nao(l, "padrao_ligado") for l in linhas)
        com_leitura = sum(not (vazio(l, "leitura_sede") and vazio(l, "leitura_poco")) for l in linhas)
        aguardando = sum(
            (sim(l, "sede") and vazio(l, "leitura_sede")) or (sim(l, "poco") and vazio(l, "leitura_poco"))
            for l in linhas
        )

        verbo = "seriam " if simular or erros else ""
        w = self.stdout.write
        w("")
        w("Resumo" + (" da simulação (nada foi gravado)" if simular else ""))
        w(f"  Início do sistema (data do histórico): {data:%d/%m/%Y}")
        w(f"  Linhas lidas: {len(registros)}")
        w(f"  Associados {verbo}criados: {criados}")
        w(f"  Associados {verbo}atualizados: {atualizados}")
        w(f"  Linhas rejeitadas: {rejeitadas}")
        w(f"  Sem CPF/CNPJ: {sem_cpf}")
        w(f"  Sem telefone: {sem_tel} (não recebem lembrete pelo WhatsApp)")
        w(f"  Sem numero_padrao: {sem_padrao}")
        w(f"  Com rede definida: {com_rede} (Sede: {na_sede}, Poço: {no_poco})")
        w(f"  Sem rede: {len(linhas) - com_rede}")
        w(f"  Padrão desligado: {padrao_desligado}")
        w(f"  Com leitura inicial: {com_leitura}")
        if aguardando:
            w(self.style.WARNING(
                f"  Rede informada sem leitura inicial: {aguardando}. A rede, o padrao_ligado e o histórico de "
                "energia ficaram de fora e eles não entram no rateio. Rode de novo quando as leituras "
                "chegarem: os mesmos registros serão atualizados."
            ))
        if "energia" in colunas:
            w("  Coluna energia ignorada: a rede vem de sede, poco e numero_padrao.")
        ignoradas = [c for c in ("isento_disponibilidade", "observacao") if c in colunas]
        if ignoradas:
            w(f"  Colunas lidas e não gravadas: {', '.join(ignoradas)} (o sistema não tem onde guardar)")

        if self.avisos:
            w(self.style.WARNING(f"  Avisos: {len(self.avisos)}"))
            for _, texto in sorted(self.avisos):
                w(self.style.WARNING(f"    {texto}"))
        if erros:
            w(self.style.ERROR(f"  Erros: {len(erros)}"))
            for _, texto in erros:
                w(self.style.ERROR(f"    {texto}"))
        elif simular:
            w(self.style.SUCCESS("  Tudo certo. Rode de novo sem --simular para gravar."))
        else:
            w(self.style.SUCCESS("  Importação concluída."))
