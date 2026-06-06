FROM python:3.12-slim

ENV HOST=0.0.0.0 \
    PORT=8080 \
    UPLOADS_DIR=/data/uploads \
    CONFIG_DIR=/data/config \
    CHUNKS_DIR=/data/chunks \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY app ./app

RUN mkdir -p /data/uploads /data/config /data/chunks

EXPOSE 8080

CMD ["python", "-m", "app.server"]
