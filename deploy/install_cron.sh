#!/usr/bin/env bash
# Cron işlərini quraşdırır (təkrar işlədilsə dublikat yaratmır).
# Cron serverin YERLİ saatı ilə işləyir (Hetzner: Asia/Baku) — vaxtlar UTC-dən çevrilir:
# hesabat 05:00 UTC (= 09:00 Bakı), AI icmalı 05:05 UTC, agentlər (kölgə) 05:10 UTC,
# uptime ayın 1-i 05:30 UTC, kölgə↔paper müqayisəsi ayın 1-i 05:35 UTC.
# Yalnız `date +%z` istifadə olunur: Ubuntu 26.04-ün uutils `date`-i `-d "05:00 UTC"`-ni
# GNU kimi çevirmir (serverdə 0 5 yazılmışdı). Yay/qış saatı olan yerdə yenidən işlət.
# Server başqa layihələrlə paylaşılır: mövcud crontab ƏVVƏLCƏ tam oxunur, sonra yazılır
# (eyni boru kəmərində oxuyub-yazmaq faylı boşalda bilər).
set -euo pipefail
dir="$(cd "$(dirname "$0")" && pwd)"
logs="$(cd "$dir/.." && pwd)/user_data/logs"
mark="# ai_trader_paper"

z="$(date +%z)"                                   # məs. +0400
off=$(( 10#${z:1:2} * 60 + 10#${z:3:2} ))
[ "${z:0:1}" = "-" ] && off=$(( -off ))
local_hm() {                                      # UTC dəqiqə (gecə yarısından) → "dəq saat" yerli
  local t=$(( ($1 + off + 1440) % 1440 ))
  echo "$(( t % 60 )) $(( t / 60 ))"
}

current="$(crontab -l 2>/dev/null | grep -v -- "$mark" || true)"
{
  [ -n "$current" ] && printf '%s\n' "$current"
  echo "$(local_hm 300) * * * $dir/daily_report.sh >> $logs/cron_report.log 2>&1 $mark"
  echo "$(local_hm 305) * * * $dir/market_brief.sh >> $logs/cron_brief.log 2>&1 $mark"
  echo "$(local_hm 310) * * * $dir/agents_shadow.sh >> $logs/cron_agents.log 2>&1 $mark"
  echo "$(local_hm 330) 1 * * $dir/monthly_uptime.sh >> $logs/cron_uptime.log 2>&1 $mark"
  echo "$(local_hm 335) 1 * * $dir/monthly_compare.sh >> $logs/cron_compare.log 2>&1 $mark"
} | crontab -
echo "Saat qurşağı sürüşməsi: $z"
crontab -l
