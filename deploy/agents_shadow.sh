#!/usr/bin/env bash
# Gündəlik agent analizi + KÖLGƏ qərar → Telegram (cron: 05:10 UTC = 09:10 Bakı, icmaldan sonra).
# Qərarlar icra olunmur; paper bot-a toxunmur. Ayrıca konteyner (profile "agents").
# Açarlar (.env): GROQ_API_KEY, LANGSMITH_API_KEY, Telegram. Əlavə arqumentlər ötürülür
# (məs. --force — eyni gündə təkrar; arqumentsiz = --send).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p user_data/shadow
args=("$@"); [ ${#args[@]} -eq 0 ] && args=(--send)
docker compose run --rm -T agents python -m agents.run "${args[@]}"
