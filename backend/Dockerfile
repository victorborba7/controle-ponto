# Imagem de desenvolvimento. A de producao entra na Etapa 12 (multi-stage, sem hot reload).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# So os requirements sao copiados: o codigo entra por bind mount (ver docker-compose.yml),
# o que mantem o hot reload funcionando e esta camada em cache.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --upgrade pip && pip install -r requirements-dev.txt

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
