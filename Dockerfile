# SamaImmo — image de production (léger : python slim, un seul process)
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# données persistantes (base SQLite, PDF, documents, sauvegardes)
RUN mkdir -p /app/data
VOLUME /app/data

ENV DATA_DIR=/app/data \
    BASE_URL=http://localhost:8000

EXPOSE 8000

# sans base de données externe, multi-worker autorisé grâce au mode WAL
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
