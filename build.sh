#!/usr/bin/env bash
# Comando de build do Render. Para a execução no primeiro erro.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
# Usa DJANGO_SUPERUSER_*; do segundo deploy em diante o usuário já existe.
python manage.py createsuperuser --no-input || true
