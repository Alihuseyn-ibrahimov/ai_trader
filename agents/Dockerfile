# Agent konteyneri — Freqtrade image-indən AYRI (bot-un mühitinə paket əlavə olunmur).
# Kod image-ə kopyalanmır: agents/, tools/, risk/, signals/ compose-da :ro mount olunur.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 HOME=/tmp
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /app
USER 1000:1000
