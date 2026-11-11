# Cópia externa do backup: Backblaze B2

Faça isto depois que o VPS estiver de pé e **antes** de colocar os dados reais.

## Por que B2, e não as outras opções

**`scp` puxado da sua máquina:** depende de você lembrar e do computador estar ligado. Backup que depende de disciplina humana falha em uns dois meses, e a pessoa só descobre no dia em que precisa.

**Google Drive:** um token do Drive no servidor dá acesso ao seu Drive inteiro. Se o VPS for invadido, vão junto seus arquivos pessoais e da faculdade. O B2 permite uma chave restrita a um bucket só.

Isso pesa porque o dump tem CPF e endereço de 65 pessoas e, pelo contrato, você é o operador desses dados.

**Custo:** o dump tem 9,4 KB e o B2 dá 10 GB grátis.

## Passo 1 — Bucket

1. Crie conta em backblaze.com, em B2 Cloud Storage.
2. **Ative 2FA.** É a chave do cofre onde ficam os dados da associação.
3. Crie um bucket, por exemplo `alfa-serra-velha-backups`, do tipo **Private**.

## Passo 2 — A regra de ciclo de vida (não pule esta)

Por padrão o B2 guarda **todas as versões** de tudo. Apagar um arquivo pelo rclone apenas o esconde. Sem esta regra, os dumps com CPF de 65 pessoas ficariam lá para sempre, o que contraria o seu papel de operador dos dados.

Nas configurações do bucket, em **Lifecycle Settings**, escolha a opção personalizada e defina:

- `daysFromUploadingToHiding`: **90**
- `daysFromHidingToDeleting`: **1**

Com isso o próprio B2 cuida da retenção: 90 dias de backups, apagados de verdade depois disso. O `backup.sh` **não** apaga nada do lado remoto, de propósito.

## Passo 3 — A chave, restrita ao bucket

Em **Application Keys**, *Add a New Application Key*:

- Nome: `servidor-alfa`
- **Allow access to Bucket:** o bucket criado, **nunca "All"**
- Tipo de acesso: *Read and Write*

Copie o `keyID` e o `applicationKey`. O segundo **só aparece uma vez**.

**Endurecimento recomendado, quando sobrar um tempo:** o console web só oferece os presets, e *Read and Write* também permite apagar. Pelo CLI do B2 dá para criar uma chave com `listBuckets,listFiles,readFiles,writeFiles` e **sem** `deleteFiles`. Combinada com o versionamento e a regra do passo 2, isso deixa o backup praticamente só de escrita: quem invadir o servidor consegue enviar e ler, mas não consegue destruir o histórico. É a proteção que vale contra ransomware.

Como o `backup.sh` não apaga nada remotamente, essa chave restrita funciona sem ajuste nenhum.

## Passo 4 — rclone no servidor, como o usuário certo

**Entre como `alfa`, não como root.** O `rclone config` grava em `~/.config/rclone/rclone.conf`, e o cron roda como `alfa`. Configurado pelo root, o cron não acha a configuração e o backup falha.

```bash
curl https://rclone.org/install.sh | sudo bash
rclone config
```

No menu: `n`, nome `b2`, tipo `b2`, cole o `keyID` em *account* e o `applicationKey` em *key*. Aceite os padrões e saia com `q`.

```bash
rclone lsd b2:
```

Tem que listar o bucket.

## Passo 5 — Aviso quando o backup falhar

Uma falha só aparece no `backup.log`, e ninguém lê log de cron. Se a chave expirar, o backup morre em silêncio e você descobre no pior dia possível.

1. Crie conta grátis em healthchecks.io.
2. Crie um check chamado `backup-alfa`, com período de 1 dia e tolerância de algumas horas.
3. Copie a URL de ping.

O `backup.sh` avisa sozinho: ping de sucesso no fim e ping de falha em qualquer erro, inclusive o dump vazio, o dump sem a marca de fim e a cópia externa que não confere. Se um dia o backup nem rodar (servidor desligado, cron quebrado), o healthchecks percebe a falta do ping e também manda e-mail.

## Passo 6 — O `.env` do servidor

```
RCLONE_REMOTO=b2:alfa-serra-velha-backups
HEALTHCHECK_URL=https://hc-ping.com/SEU-UUID-AQUI
```

Com `RCLONE_REMOTO` vazio, o script avisa a cada execução que não há cópia externa. Com `HEALTHCHECK_URL` vazio, ele avisa a cada falha que ninguém será notificado.

## Passo 7 — O teste que importa

Ver o arquivo no painel do B2 não prova nada. Teste o cenário real, em que o servidor sumiu:

```bash
cd /opt/alfa-serra-velha
bash backup.sh

# tira a cópia local de propósito
mkdir -p /tmp/guardados && mv backups/alfa-*.sql.gz /tmp/guardados/

# traz do B2 e restaura
rclone copy b2:alfa-serra-velha-backups backups/ --max-age 1h
ls -lh backups/
bash restaurar.sh backups/alfa-<data>.sql.gz
```

O `restaurar.sh` aceita caminho relativo ou absoluto, e recusa, sem apagar nada, um arquivo que não seja um dump completo.

Confirme que voltaram os 65 associados. Só depois disso o backup está pronto, e só depois disso entram os dados reais.

## Guarde fora do servidor

Se o VPS se perder, você vai precisar destas coisas, e elas não podem estar só nele:

- `keyID` e `applicationKey` do B2
- Nome do bucket
- A `POSTGRES_PASSWORD` do `.env`
- A URL do healthchecks

Num gerenciador de senhas. Não no servidor, nem no GitHub.
