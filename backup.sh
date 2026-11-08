#!/usr/bin/env bash
# Backup do banco de dados. Roda todo dia pelo cron (ver instalar-backup.sh).
#
# IMPORTANTE: um backup guardado no mesmo servidor NAO e um backup de verdade.
# Se o VPS for perdido, os dois somem juntos. Configure a copia externa
# no fim deste arquivo.

set -o errexit
set -o nounset
set -o pipefail

# Para testar na sua maquina: PASTA="$PWD" bash backup.sh
PASTA="${PASTA:-/opt/alfa-serra-velha}"
DESTINO="${PASTA}/backups"
DIAS_PARA_GUARDAR=30

cd "$PASTA"

# Le POSTGRES_USER e POSTGRES_DB do .env sem expor a senha no processo.
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)"

mkdir -p "$DESTINO"
ARQUIVO="${DESTINO}/alfa-$(date +%Y-%m-%d_%H%M).sql.gz"

echo "$(date '+%Y-%m-%d %H:%M') iniciando backup"

# -T desliga o terminal interativo, necessario no cron.
docker compose exec -T db \
    pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$ARQUIVO"

# Um dump valido nunca sai minusculo. Se saiu, algo falhou: apaga e avisa.
TAMANHO=$(stat -c%s "$ARQUIVO")
if [ "$TAMANHO" -lt 1024 ]; then
    rm -f "$ARQUIVO"
    echo "ERRO: o backup saiu com ${TAMANHO} bytes, parece vazio. Nada foi guardado." >&2
    exit 1
fi

echo "$(date '+%Y-%m-%d %H:%M') backup ok: ${ARQUIVO} (${TAMANHO} bytes)"

# Apaga os backups antigos.
find "$DESTINO" -name 'alfa-*.sql.gz' -mtime "+${DIAS_PARA_GUARDAR}" -delete

# --- COPIA EXTERNA -----------------------------------------------------------
# Escolha UMA das opcoes e descomente.
#
# Opcao A - Backblaze B2 ou Google Drive, pelo rclone (instale com: curl https://rclone.org/install.sh | sudo bash)
#   rclone copy "$ARQUIVO" remoto:alfa-serra-velha/backups --no-traverse
#
# Opcao B - puxar da sua maquina, agendado no SEU computador:
#   scp alfa@IP_DO_SERVIDOR:/opt/alfa-serra-velha/backups/*.sql.gz ~/backups-alfa/
#
# Sem uma dessas, voce tem copia do banco mas nao tem protecao contra perder o servidor.
