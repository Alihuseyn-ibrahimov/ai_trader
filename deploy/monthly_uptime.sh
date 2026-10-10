#!/usr/bin/env bash
# Aylıq: heartbeat logundan vaxtında emal olunmuş 4h şamları uptime_candles.csv-yə yığır
# (log faylları fırlanır — köhnə log silinməzdən əvvəl qeyd olunmalıdır). Son 60 gün.
set -euo pipefail
cd "$(dirname "$0")/.."
start="$(date -u -d '60 days ago' +%Y-%m-%dT00:00)"
docker compose exec -T paper python /freqtrade/tools/uptime.py --start "$start" || true
