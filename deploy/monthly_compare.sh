#!/usr/bin/env bash
# Aylıq: kölgə portfel (agentlər) ↔ TrendEmaAtr paper müqayisəsi → Telegram
# (cron: ayın 1-i 05:35 UTC = 09:35 Bakı). Ticarətə toxunmur — DB yalnız oxunur.
# Əlavə arqumentlər ötürülür (məs. --start 2026-10-19; arqumentsiz = --send).
set -euo pipefail
cd "$(dirname "$0")/.."
args=("$@"); [ ${#args[@]} -eq 0 ] && args=(--send)
docker compose exec -T paper python /freqtrade/tools/shadow_compare.py "${args[@]}"
