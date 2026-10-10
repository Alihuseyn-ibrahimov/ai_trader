#!/usr/bin/env bash
# Cron işlərini quraşdırır (təkrar işlədilsə dublikat yaratmır).
# Cron serverin YERLİ saatı ilə işləyir (Hetzner: Asia/Baku) — vaxtlar UTC-dən çevrilir:
# hesabat 05:00 UTC (= 09:00 Bakı), uptime ayın 1-i 05:30 UTC.
# Server başqa layihələrlə paylaşılır: mövcud crontab ƏVVƏLCƏ tam oxunur, sonra yazılır
# (eyni boru kəmərində oxuyub-yazmaq faylı boşalda bilər).
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
logs="$(cd "$dir/.." && pwd)/user_data/logs"
mark="# ai_trader_paper"
local_hm() { date -d "$1 UTC" '+%-M %-H'; }   # "05:00" UTC → "dəqiqə saat" yerli vaxtla
current="$(crontab -l 2>/dev/null | grep -v -- "$mark" || true)"
{
  [ -n "$current" ] && printf '%s\n' "$current"
  echo "$(local_hm 05:00) * * * $dir/daily_report.sh >> $logs/cron_report.log 2>&1 $mark"
  echo "$(local_hm 05:30) 1 * * $dir/monthly_uptime.sh >> $logs/cron_uptime.log 2>&1 $mark"
} | crontab -
crontab -l
