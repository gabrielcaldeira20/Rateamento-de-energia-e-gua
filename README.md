# Sistema de Gestão Financeira — Associação Alfa Serra Velha

Monolito Django com templates, PostgreSQL em produção e hospedagem num VPS com Docker.
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

## Publicar no VPS

São três contêineres, definidos no `docker-compose.yml`: o banco (PostgreSQL 16, sem porta aberta
para fora), a aplicação (Django com gunicorn) e o Caddy, que emite o certificado HTTPS sozinho e
serve os arquivos estáticos. Um VPS Ubuntu 22.04 ou 24.04 com 1 ou 2 GB de memória basta.

1. **Domínio:** crie um registro A apontando o domínio para o IP do VPS.
2. **Preparar o servidor**, como root, uma única vez. O script atualiza o sistema, liga as
   atualizações automáticas de segurança, acerta o fuso para Brasília, cria swap, instala o Docker,
   liga o firewall (só SSH, HTTP e HTTPS) e cria o usuário `alfa`:

   ```bash
   scp instalar-vps.sh root@IP_DO_SERVIDOR:
   ssh root@IP_DO_SERVIDOR bash instalar-vps.sh
   ```

3. **Baixar o projeto**, já como o usuário `alfa`. Se o repositório for privado, cadastre no GitHub
   uma *deploy key* somente leitura para o servidor:

   ```bash
   ssh alfa@IP_DO_SERVIDOR
   git clone URL_DO_REPOSITORIO /opt/alfa-serra-velha
   cd /opt/alfa-serra-velha
   cp .env.example .env && chmod 600 .env
   nano .env
   ```

   No `.env`, preencha `DOMINIO`, `ACME_EMAIL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` (com `https://`),
   `SECRET_KEY`, `POSTGRES_PASSWORD` e `DJANGO_SUPERUSER_PASSWORD`. Os comandos para gerar a chave e a
   senha estão no próprio arquivo. `DEBUG` fica `False`. O `.env` nunca vai para o GitHub.

4. **Subir:**

   ```bash
   docker compose up -d --build
   docker compose logs web     # migrações, collectstatic e "Listening at: http://0.0.0.0:8000"
   ```

   O administrador é criado na primeira subida com as variáveis `DJANGO_SUPERUSER_*`.
   Acesse `https://SEU_DOMINIO` e entre com ele.

5. **Backup diário:** `bash instalar-backup.sh` agenda o backup para 03:17. Rode `bash backup.sh` uma vez
   na hora para conferir. Falta configurar a cópia externa, veja a seção **Backup**.

6. **Importar os associados.** A planilha tem dados pessoais: ela vai direto por `scp`, é importada e é
   apagada do servidor. Rode sempre primeiro com `--simular`:

   ```bash
   # na sua máquina
   scp associados-para-importar.csv alfa@IP_DO_SERVIDOR:/opt/alfa-serra-velha/
   # no servidor
   docker compose cp associados-para-importar.csv web:/app/
   docker compose exec web python manage.py importar_associados associados-para-importar.csv --data-inicio AAAA-MM-01 --simular
   docker compose exec web python manage.py importar_associados associados-para-importar.csv --data-inicio AAAA-MM-01
   docker compose exec web rm /app/associados-para-importar.csv
   rm associados-para-importar.csv
   ```

7. **Ensaiar a restauração** antes de depender dela: siga a seção **Backup**.

8. **Fechar o acesso do root:** depois de confirmar que entra como `alfa`, defina `PermitRootLogin no` e
   `PasswordAuthentication no` em `/etc/ssh/sshd_config` e rode `sudo systemctl restart ssh`.

**Atualizar o sistema** depois de um envio para o GitHub:

```bash
cd /opt/alfa-serra-velha
bash backup.sh
git pull
docker compose up -d --build
```

As migrações rodam sozinhas a cada subida do contêiner da aplicação.

**HTTPS:** o Caddy emite e renova o certificado da Let's Encrypt e redireciona HTTP para HTTPS.
Ele também envia o cabeçalho HSTS de um ano. O Django marca os cookies de sessão e CSRF como seguros
e confia no cabeçalho `X-Forwarded-Proto` que o Caddy repassa.

**Testar na sua máquina** antes do servidor: use no `.env` `DOMINIO=:80`, `DEBUG=True`,
`ALLOWED_HOSTS=localhost,127.0.0.1` e `CSRF_TRUSTED_ORIGINS=http://localhost`, e acesse `http://localhost`.
Para testar o modo produção, `DOMINIO=localhost`, `DEBUG=False` e `CSRF_TRUSTED_ORIGINS=https://localhost`;
o navegador vai reclamar do certificado próprio do Caddy, o que é esperado.

## Carga inicial e exportação

- **Importar a planilha oficial da associação:** `python manage.py importar_associados ARQUIVO.csv
  --data-inicio AAAA-MM-01 --simular`, e depois sem `--simular`. A data é o dia 1 do mês em que o sistema
  entra em operação. Procura por CPF/CNPJ, depois pelo número do padrão e por último pelo nome, então rodar
  de novo atualiza em vez de duplicar. Rede sem leitura inicial não é ligada, só gera aviso. As colunas
  estão no começo do arquivo `associados/management/commands/importar_associados.py`.
- **Importar associados das planilhas antigas:** `python manage.py importar_planilhas associados.csv`.
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

- **`backup.sh`** gera `backups/alfa-AAAA-MM-DD_HHMM.sql.gz` com o `pg_dump` do banco, recusa arquivos
  suspeitos de vazios e apaga os de mais de 30 dias. O `instalar-backup.sh` o agenda para todo dia às 03:17,
  com registro em `backups/backup.log`.
- **`restaurar.sh ARQUIVO`** pede a confirmação `RESTAURAR`, guarda antes um dump do estado atual,
  recria o banco e restaura. Ele para no primeiro erro e, nesse caso, deixa a aplicação parada e mostra
  o comando para voltar ao estado anterior.
- **Cópia externa: ainda não configurada.** Hoje os backups ficam só no próprio VPS. Se o servidor for
  perdido, eles vão junto. As opções estão comentadas no fim do `backup.sh`.

Ensaio de restauração, para fazer no servidor antes de precisar:

```bash
bash backup.sh
bash restaurar.sh backups/alfa-AAAA-MM-DD_HHMM.sql.gz   # o arquivo que acabou de ser gerado
```

Depois, abra o sistema e confira os associados. Na sua máquina, os dois scripts rodam com
`PASTA="$PWD" bash backup.sh` e `PASTA="$PWD" bash restaurar.sh ARQUIVO`.

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
