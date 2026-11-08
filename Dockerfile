FROM python:3.12-slim

# PYTHONUNBUFFERED faz o log aparecer na hora no "docker compose logs".
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libpq5 e o cliente do PostgreSQL que o psycopg precisa em tempo de execucao.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia so o requirements primeiro: assim o Docker reaproveita a camada de
# instalacao quando mudar apenas o codigo.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Roda como usuario comum, nao como root.
RUN useradd --create-home appuser \
    && mkdir -p /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
