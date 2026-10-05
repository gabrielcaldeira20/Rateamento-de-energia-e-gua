# Sistema de Gestão Financeira — Associação Alfa Serra Velha

Monolito Django com templates, PostgreSQL em produção e hospedagem no Render.
Há um único usuário, o tesoureiro, com login real do Django.

## Rodar localmente

Requisitos: Python 3.12 ou mais novo.

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows (Git Bash: source .venv/Scripts/activate)
# source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
export DEBUG=True               # PowerShell: $env:DEBUG = "True"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Sem a variável `DATABASE_URL`, o projeto usa SQLite no arquivo `db.sqlite3`.
Isso serve só para desenvolvimento. Para testar com PostgreSQL local, defina
`DATABASE_URL=postgresql://usuario:senha@localhost:5432/asv`.

Testes:

```bash
DEBUG=True python manage.py test
```

## Publicar no Render

São dois recursos: um PostgreSQL e um Web Service. Os planos Starter evitam que o
serviço hiberne e que o banco gratuito expire. Confira os preços atuais no site do Render.

1. Suba este repositório para o GitHub.
2. No Render, crie um **PostgreSQL**. Depois de criado, copie a **Internal Database URL**.
3. Crie um **Web Service** ligado ao repositório, com ambiente Python.
4. Comando de build: `./build.sh`
   (equivale a `pip install -r requirements.txt && python manage.py collectstatic --no-input && python manage.py migrate`).
5. Comando de início: `gunicorn config.wsgi:application`
6. Em **Environment**, cadastre as variáveis do arquivo `.env.example`:

   | Variável | Valor |
   |---|---|
   | `SECRET_KEY` | chave longa e aleatória (veja o comando no `.env.example`) |
   | `DEBUG` | `False` |
   | `DATABASE_URL` | Internal Database URL do passo 2 |
   | `ALLOWED_HOSTS` | `nome-do-servico.onrender.com` |
   | `CSRF_TRUSTED_ORIGINS` | `https://nome-do-servico.onrender.com` |
   | `PYTHON_VERSION` | `3.13.5` |

7. Faça o primeiro deploy. Depois, abra o **Shell** do serviço e crie o usuário do tesoureiro:

   ```bash
   python manage.py createsuperuser
   ```

8. Ative o deploy automático a cada envio para a branch principal.

O HTTPS é fornecido pelo Render no endereço `onrender.com`. Em produção, os cookies de
sessão e CSRF são marcados como seguros e o tráfego HTTP é redirecionado para HTTPS.
O HSTS fica desligado por padrão. Para ligar, defina `SECURE_HSTS_SECONDS` (por exemplo, `31536000`)
depois de confirmar que o site funciona só por HTTPS.

## Carga inicial e exportação

- **Importar associados das planilhas:** `python manage.py importar_planilhas associados.csv`.
  Use `--simular` para validar sem gravar. O formato está em `docs/exemplo_associados.csv`.
  Se uma linha tiver erro, nada é gravado. Nomes já cadastrados são ignorados.
- **Exportar os dados da associação:** `python manage.py exportar_dados --destino pasta`.
  Gera CSVs de associados, cobranças, pagamentos, despesas, fechamentos e leituras.
  Os associados importados recebem no histórico de ligações a data do dia da importação.
  Para incluir alguém em rateios de meses anteriores, ajuste a data na linha do tempo do associado.

## Histórico de ligações

Cada mudança de rede (Sede, Poço) ou de água é um registro com data, no menu **Histórico de ligações**
ou na página do associado. Aceita registros retroativos e duas mudanças do mesmo serviço no mesmo dia
viram um único registro.

- O estado atual do associado é sempre o registro mais recente por data de cada serviço.
- O lançamento de energia de um mês só lista quem estava com a rede ligada no último dia daquele mês.
- A geração mensal só cria água para quem a tinha ligada no último dia do mês.
- Fechamentos e cobranças já criados nunca são recalculados.

Na atualização para esta versão, a migração `associados 0003` cria um registro para cada serviço já
ligado, com a data mais antiga entre o cadastro do associado e suas leituras e cobranças.

## Exportação do relatório financeiro

Na tela do relatório, os botões **Exportar PDF** e **Exportar CSV** usam o regime e o período selecionados.
Os números vêm das mesmas funções da tela. O CSV usa UTF-8 com BOM, ponto e vírgula e valores no formato
1.234,56, e abre direto no Excel em português. O PDF é gerado com reportlab, sem pacotes do sistema.

## Backup

Confira no painel do Render a política de backup do plano do PostgreSQL contratado.
Como reforço, guarde um `pg_dump` mensal fora do Render:

```bash
pg_dump "$DATABASE_URL" --format=custom --file=asv-$(date +%Y-%m).dump
```

## Organização do código

| App | Responsabilidade |
|---|---|
| `config` | Configurações, rotas gerais, WSGI |
| `core` | Configuração da associação, painel inicial, login, utilitários, comandos |
| `associados` | Cadastro, inativação e reativação, leituras iniciais, histórico de ligações |
| `energia` | Fechamento mensal em 3 passos: rateio, disponibilidade, multa e validações |
| `cobrancas` | Geração mensal, pagamentos, crédito, baixa em lote, link do WhatsApp |
| `despesas` | Cadastro e filtros de despesas |
| `relatorios` | Relatório financeiro e exportação em PDF e CSV |

As regras de cálculo ficam em `services.py` de cada app, não nas views.
Operações que gravam vários registros usam `transaction.atomic`.
O andamento de cada fase está em `STATUS.md`.
