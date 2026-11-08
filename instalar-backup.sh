#!/usr/bin/env bash
# Agenda o backup diario. Rode uma vez, como o usuario do projeto:
#     bash instalar-backup.sh

set -o errexit
set -o nounset

PASTA="/opt/alfa-serra-velha"
LINHA="17 3 * * * cd ${PASTA} && bash backup.sh >> ${PASTA}/backups/backup.log 2>&1"

if crontab -l 2>/dev/null | grep -qF "backup.sh"; then
    echo "O backup ja esta agendado. Agenda atual:"
    crontab -l | grep "backup.sh"
    exit 0
fi

(crontab -l 2>/dev/null; echo "$LINHA") | crontab -
echo "Backup agendado para todo dia as 03:17."
echo "O registro de cada execucao fica em ${PASTA}/backups/backup.log"
echo
echo "Teste agora, sem esperar o horario:"
echo "  cd ${PASTA} && bash backup.sh"
