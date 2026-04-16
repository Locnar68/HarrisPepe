# Cloud Run sync image — Python-only.
# Build context MUST be the repo root so that COPY can grab core/ connectors/ ingestion/ metadata/ vertex/.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY cloud_run/requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY core/         /app/core/
COPY connectors/   /app/connectors/
COPY ingestion/    /app/ingestion/
COPY metadata/     /app/metadata/
COPY vertex/       /app/vertex/
COPY bootstrap/    /app/bootstrap/
COPY config/       /app/config/
COPY cloud_run/main.py /app/main.py

ENV PORT=8080
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 1700 main:app
