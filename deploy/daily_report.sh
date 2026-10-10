#!/usr/bin/env bash
# Gündəlik paper hesabatı → Telegram (cron: hər gün 05:00 UTC = 09:00 Bakı).
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose exec -T paper python /freqtrade/tools/paper_report.py --send
