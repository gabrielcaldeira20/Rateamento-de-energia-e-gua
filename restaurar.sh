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
SEGURANCA=""
# Em que ponto o script esta: a mensagem de erro depende disso.
SEGURANCA_OK=0   # 1 depois que o dump de seguranca terminou inteiro
BANCO_MEXIDO=0   # 1 a partir do momento em que a aplicacao foi parada

ao_falhar() {
    echo >&2
    echo "=====================================================================" >&2
    echo "ERRO: a restauracao NAO foi concluida." >&2
    echo >&2
    if [ "$BANCO_MEXIDO" -eq 0 ]; then
        echo "A falha foi antes de tocar no banco: os dados atuais continuam" >&2
        echo "intactos e a aplicacao continua no ar." >&2
        if [ -n "$SEGURANCA" ] && [ -f "$SEGURANCA" ]; then
            echo "O dump de seguranca ficou incompleto e foi apagado." >&2
            rm -f "$SEGURANCA"
        fi
    else
        echo "A aplicacao esta parada de proposito, para nao rodar em cima de um" >&2
        echo "banco pela metade. O banco pode estar incompleto AGORA." >&2
        if [ "$SEGURANCA_OK" -eq 1 ]; then
            echo >&2
            echo "Para voltar ao estado de antes desta tentativa:" >&2
            echo "  bash restaurar.sh \"${SEGURANCA}\"" >&2
        fi
        echo >&2
        echo "Para subir a aplicacao assim mesmo (so se voce souber o que esta fazendo):" >&2
        echo "  docker compose start web" >&2
    fi
    echo "=====================================================================" >&2
}
trap ao_falhar ERR

if [ -z "$ARQUIVO" ]; then
    trap - ERR
    echo "Uso: bash restaurar.sh CAMINHO_DO_BACKUP.sql.gz" >&2
    echo >&2
    echo "Backups disponiveis:" >&2
    ls -lh "${PASTA}/backups/" 2>/dev/null || echo "  (nenhum)" >&2
    exit 1
fi

if [ ! -f "$ARQUIVO" ]; then
    trap - ERR
    echo "ERRO: arquivo nao encontrado: ${ARQUIVO}" >&2
    exit 1
fi
# Caminho absoluto: o script muda de pasta logo abaixo.
ARQUIVO="$(realpath "$ARQUIVO")"

cd "$PASTA"
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | cut -d= -f2-)"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | cut -d= -f2-)"

echo "Isto vai APAGAR o banco atual (${POSTGRES_DB}) e restaurar:"
echo "  ${ARQUIVO}"
read -r -p "Digite RESTAURAR para confirmar: " RESPOSTA
if [ "$RESPOSTA" != "RESTAURAR" ]; then
    trap - ERR
    echo "Cancelado."
    exit 0
fi

# Antes de qualquer coisa, guarda um dump do estado atual.
# Com segundos no nome: restaurar a partir de um "antes-da-restauracao" logo apos
# uma falha nao pode gerar um arquivo com o mesmo nome e sobrescrever o backup
# que esta sendo restaurado.
SEGURANCA="${PASTA}/backups/antes-da-restauracao-$(date +%Y-%m-%d_%H%M%S).sql.gz"
if [ "$(realpath "$ARQUIVO")" = "$(realpath -m "$SEGURANCA")" ]; then
    trap - ERR
    echo "ERRO: o dump de seguranca teria o mesmo nome do backup a restaurar. Rode de novo." >&2
    exit 1
fi
mkdir -p "${PASTA}/backups"
echo "==> Salvando o estado atual em ${SEGURANCA}"
docker compose exec -T db \
    pg_dump --no-owner --no-privileges -U "$POSTGRES_USER" "$POSTGRES_DB" \
    | gzip > "$SEGURANCA"
SEGURANCA_OK=1

echo "==> Parando a aplicacao"
BANCO_MEXIDO=1
docker compose stop web

echo "==> Recriando o banco"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS ${POSTGRES_DB};"
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER};"

# ON_ERROR_STOP=1 faz o psql parar e devolver erro no primeiro problema.
# Sem isso ele ignora as falhas, termina com sucesso, e uma restauracao
# pela metade passa por concluida. Com errexit e pipefail, o script para aqui.
echo "==> Restaurando os dados"
gunzip -c "$ARQUIVO" | docker compose exec -T db \
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"

echo "==> Subindo a aplicacao"
docker compose start web

trap - ERR
echo
echo "Restauracao concluida. Abra o sistema e confira os dados."
echo "O estado anterior ficou guardado em: ${SEGURANCA}"
