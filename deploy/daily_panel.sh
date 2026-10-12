#!/usr/bin/env bash
# Gündəlik HTML panel → Telegram (fayl kimi; cron: 05:15 UTC = 09:15 Bakı, agentlərdən sonra).
# Ticarətə toxunmur — DB/CSV yalnız oxunur; yazılan yeganə fayl user_data/panel.html.
# Arqumentsiz = --send; əl ilə baxış üçün boş arqument ("") ver və faylı scp ilə götür.
set -euo pipefail
cd "$(dirname "$0")/.."
args=("$@"); [ ${#args[@]} -eq 0 ] && args=(--send)
docker compose exec -T paper python /freqtrade/tools/panel.py "${args[@]}"
