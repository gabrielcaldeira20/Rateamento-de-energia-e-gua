#!/usr/bin/env bash
# Backup do banco de dados. Roda todo dia pelo cron (ver instalar-backup.sh).
#
# Guarda uma copia local e, se RCLONE_REMOTO estiver definido no .env,
# manda outra para fora do servidor. A copia local sozinha nao protege
# contra perder o VPS: as duas somem juntas.
#
# A retencao do lado remoto NAO e feita aqui. Ela fica na regra de ciclo de
# vida do bucket, no proprio B2 (ver BACKUP-EXTERNO-B2.md). Assim a chave do
# servidor nao precisa de permissao para apagar, e quem invadir o servidor
# nao consegue destruir o historico de backups.

set -o errexit
set -o nounset
set -o pipefail

PASTA="${PASTA:-/opt/alfa-serra-velha}"
DESTINO="${PASTA}/backups"
DIAS_LOCAL=30
DIAS_SEGURANCA=90

cd "$PASTA"

valor_do_env() { grep -E "^$1=" .env | cut -d= -f2- || true; }

POSTGRES_USER="$(valor_do_env POSTGRES_USER)"
POSTGRES_DB="$(valor_do_env POSTGRES_DB)"
RCLONE_REMOTO="$(valor_do_env RCLONE_REMOTO)"
HEALTHCHECK_URL="$(valor_do_env HEALTHCHECK_URL)"

# Avisa um servico externo se o backup falhar. Sem isso, uma falha so aparece
# no backup.log, que ninguem le, e o backup pode estar morto ha meses.
PARCIAL=""

ao_sair() {
    codigo=$?
    # Dump que nao terminou nunca fica com nome de backup valido: numa emergencia,
    # "restaurar o mais recente" pegaria um arquivo vazio.
    if [ -n "$PARCIAL" ] && [ -f "$PARCIAL" ]; then
        rm -f "$PARCIAL"
    fi
    if [ -n "$HEALTHCHECK_URL" ]; then
        if [ "$codigo" -eq 0 ]; then
            curl -fsS -m 10 --retry 3 -o /dev/null "$HEALTHCHECK_URL" || true
        else
            curl -fsS -m 10 --retry 3 -o /dev/null "${HEALTHCHECK_URL}/fail" || true
        fi
    elif [ "$codigo" -ne 0 ]; then
        echo "  AVISO: HEALTHCHECK_URL vazio, ninguem sera avisado desta falha." >&2
    fi
}
trap ao_sair EXIT

mkdir -p "$DESTINO"
ARQUIVO="${DESTINO}/alfa-$(date +%Y-%m-%d_%H%M%S).sql.gz"
# O dump e gravado com outro nome e so vira alfa-*.sql.gz depois de conferido.
PARCIAL="${ARQUIVO}.parcial"

echo "$(date '+%Y-%m-%d %H:%M') iniciando backup"

# -T desliga o terminal interativo, necessario no cron.
docker compose exec -T db \
    pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$PARCIAL"

# Um dump valido nunca sai minusculo. Se saiu, algo falhou.
TAMANHO=$(stat -c%s "$PARCIAL")
if [ "$TAMANHO" -lt 1024 ]; then
    echo "ERRO: o backup saiu com ${TAMANHO} bytes, parece vazio. Nada foi guardado." >&2
    exit 1
fi
# O pg_dump escreve esta linha no fim. Sem ela, o dump foi cortado no meio.
FINAL_DO_DUMP="$(gunzip -c "$PARCIAL" | tail -n 5)"
if ! printf '%s\n' "$FINAL_DO_DUMP" | grep -q "PostgreSQL database dump complete"; then
    echo "ERRO: o backup nao termina com a marca de dump completo. Nada foi guardado." >&2
    exit 1
fi
mv "$PARCIAL" "$ARQUIVO"
PARCIAL=""
echo "  copia local ok: ${ARQUIVO} (${TAMANHO} bytes)"

# --- Copia externa -----------------------------------------------------------
# Defina no .env, por exemplo:  RCLONE_REMOTO=b2:alfa-serra-velha-backups
if [ -z "$RCLONE_REMOTO" ]; then
    echo "  AVISO: RCLONE_REMOTO vazio no .env, sem copia externa." >&2
    echo "  O backup existe so neste servidor. Se ele for perdido, os dados vao junto." >&2
elif ! command -v rclone >/dev/null 2>&1; then
    echo "ERRO: RCLONE_REMOTO definido, mas o rclone nao esta instalado." >&2
    exit 1
else
    echo "  enviando para ${RCLONE_REMOTO}"
    rclone copy "$ARQUIVO" "$RCLONE_REMOTO" --no-traverse

    # Confere que chegou mesmo, com o tamanho certo. Enviar sem conferir
    # da a mesma falsa sensacao de seguranca que um backup nao restaurado.
    REMOTO=$(rclone size "${RCLONE_REMOTO}/$(basename "$ARQUIVO")" --json 2>/dev/null \
             | grep -oE '"bytes":[0-9]+' | cut -d: -f2 || echo 0)
    if [ "$REMOTO" != "$TAMANHO" ]; then
        echo "ERRO: a copia externa nao confere (local ${TAMANHO}, remoto ${REMOTO})." >&2
        exit 1
    fi
    echo "  copia externa confirmada: ${REMOTO} bytes"
fi

# --- Limpeza local -----------------------------------------------------------
find "$DESTINO" -name 'alfa-*.sql.gz' -mtime "+${DIAS_LOCAL}" -delete
# Os dumps tirados antes de uma restauracao sao raros e valiosos: guarda mais tempo.
find "$DESTINO" -name 'antes-da-restauracao-*.sql.gz' -mtime "+${DIAS_SEGURANCA}" -delete

echo "$(date '+%Y-%m-%d %H:%M') backup concluido"
