#!/usr/bin/env bash
# Restaura o banco a partir de um backup.
#
# Uso:
#     bash restaurar.sh /opt/alfa-serra-velha/backups/alfa-2026-11-07_0300.sql.gz
#
# ATENCAO: isto APAGA os dados atuais e coloca os do backup no lugar.
# Teste este procedimento ANTES de precisar dele. Um backup que nunca foi
# restaurado e so um arquivo: voce nao sabe se funciona.

set -o errexit
set -o nounset
set -o pipefail

# Para testar na sua maquina: PASTA="$PWD" bash restaurar.sh backups/ARQUIVO.sql.gz
PASTA="${PASTA:-/opt/alfa-serra-velha}"
ARQUIVO="${1:-}"

if [ -z "$ARQUIVO" ]; then
    echo "Uso: bash restaurar.sh CAMINHO_DO_BACKUP.sql.gz" >&2
    echo >&2
    echo "Backups disponiveis:" >&2
    ls -lh "${PASTA}/backups/" 2>/dev/null || echo "  (nenhum)" >&2
    exit 1
fi

if [ ! -f "$ARQUIVO" ]; then
    echo "ERRO: arquivo nao encontrado: ${ARQUIVO}" >&2
    exit 1
fi

cd "$PASTA"
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)"

echo "Isto vai APAGAR o banco atual (${POSTGRES_DB}) e restaurar:"
echo "  ${ARQUIVO}"
read -r -p "Digite RESTAURAR para confirmar: " RESPOSTA
if [ "$RESPOSTA" != "RESTAURAR" ]; then
    echo "Cancelado."
    exit 0
fi

# Antes de qualquer coisa, guarda um dump do estado atual.
SEGURANCA="${PASTA}/backups/antes-da-restauracao-$(date +%Y-%m-%d_%H%M).sql.gz"
echo "==> Salvando o estado atual em ${SEGURANCA}"
docker compose exec -T db \
    pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$SEGURANCA"

echo "==> Parando a aplicacao"
docker compose stop web

echo "==> Recriando o banco"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

echo "==> Restaurando os dados"
gunzip -c "$ARQUIVO" | docker compose exec -T db \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "==> Subindo a aplicacao"
docker compose start web

echo
echo "Restauracao concluida. Abra o sistema e confira os dados."
echo "O estado anterior ficou guardado em: ${SEGURANCA}"
