#!/usr/bin/env bash
# Gündəlik AI bazar icmalı → Telegram (cron: 05:05 UTC = 09:05 Bakı, hesabatdan sonra).
# Ticarətə toxunmur — yalnız oxuyur və mesaj göndərir.
# GROQ_API_KEY .env-dən oxunur və YALNIZ bu prosesə ötürülür (bot-un mühitinə yox; bot-u
# restart etmək lazım deyil). `-e AD` dəyəri mühitdən götürür — komanda sətrində görünmür.
set -euo pipefail
cd "$(dirname "$0")/.."
GROQ_API_KEY="$(grep -E '^GROQ_API_KEY=' .env | cut -d= -f2- || true)"
export GROQ_API_KEY
docker compose exec -T -e GROQ_API_KEY paper python /freqtrade/tools/market_brief.py --send
