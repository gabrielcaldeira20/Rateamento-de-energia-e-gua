#!/usr/bin/env bash
# Comando de build do Render. Para a execução no primeiro erro.
set -o errexit

pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate
