#!/usr/bin/env bash
# Cron işlərini quraşdırır (təkrar işlədilsə dublikat yaratmır). Server UTC-dədir.
# Server başqa layihələrlə paylaşılır: mövcud crontab ƏVVƏLCƏ tam oxunur, sonra yazılır
# (eyni boru kəmərində oxuyub-yazmaq faylı boşalda bilər).
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
logs="$(cd "$dir/.." && pwd)/user_data/logs"
mark="# ai_trader_paper"
current="$(crontab -l 2>/dev/null | grep -v -- "$mark" || true)"
{
  [ -n "$current" ] && printf '%s\n' "$current"
  echo "0 5 * * * $dir/daily_report.sh >> $logs/cron_report.log 2>&1 $mark"
  echo "30 5 1 * * $dir/monthly_uptime.sh >> $logs/cron_uptime.log 2>&1 $mark"
} | crontab -
crontab -l
