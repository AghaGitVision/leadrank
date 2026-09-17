FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

ENV LEADRANK_ENV=production \
    LEADRANK_SCAN_MODE=live \
    PORT=8080

EXPOSE 8080

# Cloud Run sets $PORT; uvicorn reads it via shell expansion.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
