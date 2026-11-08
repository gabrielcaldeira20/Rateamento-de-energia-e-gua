#!/usr/bin/env bash
# Roda a cada inicializacao do conteiner da aplicacao.
set -o errexit

echo ">> Aplicando migracoes..."
python manage.py migrate --no-input

echo ">> Coletando arquivos estaticos..."
python manage.py collectstatic --no-input

# Cria o administrador na primeira vez, usando as variaveis DJANGO_SUPERUSER_*.
# Nas proximas vezes o usuario ja existe e o comando falha, por isso o "|| true".
echo ">> Garantindo o usuario administrador..."
python manage.py createsuperuser --no-input || true

echo ">> Subindo o gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
