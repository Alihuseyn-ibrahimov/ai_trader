"""Faza 1, meyar 7 — işləmə: 4h şamların ≥ 98%-i vaxtında emal olunubmu?

Şam vaxtında sayılır, əgər onun açılışından sonra 15 dəqiqə ərzində bot-un
`state='RUNNING'` heartbeat-i varsa (Freqtrade hər dəqiqə yazır). Log faylları
fırlandığı (rotation) üçün emal olunmuş şamlar `uptime_candles.csv`-də yığılır —
alət hər ay işlədilməlidir ki, köhnə log silinməzdən əvvəl qeyd olunsun.

    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/uptime.py --start 2026-11-01
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

LOG_DIR = Path("/freqtrade/user_data/logs")
LOG_GLOB = "paper.log*"
STORE = Path("/freqtrade/user_data/uptime_candles.csv")
CANDLE = pd.Timedelta(hours=4)
GRACE = pd.Timedelta(minutes=15)
MIN_UPTIME = 0.98

_HEARTBEAT = re.compile(
    r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),\d+ - freqtrade\.worker - INFO - Bot heartbeat\..*state='RUNNING'"
)


def parse_heartbeats(lines) -> list[pd.Timestamp]:
    out = []
    for line in lines:
        m = _HEARTBEAT.match(line)
        if m:
            out.append(pd.Timestamp(m.group(1), tz="UTC"))
    return out


def candle_coverage(heartbeats: list[pd.Timestamp], start: pd.Timestamp, end: pd.Timestamp,
                    candle: pd.Timedelta = CANDLE, grace: pd.Timedelta = GRACE) -> tuple[set, int]:
    """[start, end) aralığındakı şamlardan hansıları vaxtında emal olunub; ümumi şam sayı."""
    opens = pd.date_range(start, end, freq=candle, inclusive="left")
    hb = pd.Series(sorted(heartbeats), dtype="datetime64[ns, UTC]")
    covered = set()
    for t in opens:
        if ((hb >= t) & (hb < t + grace)).any():
            covered.add(t)
    return covered, len(opens)


def merge_covered(path: Path, new: set) -> set:
    old = set()
    if path.exists():
        old = set(pd.to_datetime(pd.read_csv(path)["candle"], utc=True))
    allc = old | set(new)
    pd.DataFrame({"candle": sorted(allc)}).to_csv(path, index=False)
    return allc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="T0")
    parser.add_argument("--end", default=None, help="default: indi (son tam şama qədər)")
    args = parser.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC") if args.end else pd.Timestamp.now(tz="UTC").floor("4h")
    lines = []
    for f in sorted(LOG_DIR.glob(LOG_GLOB)):
        lines.extend(f.read_text(errors="replace").splitlines())
    covered_now, _ = candle_coverage(parse_heartbeats(lines), start, end)
    covered = {c for c in merge_covered(STORE, covered_now) if start <= c < end}
    total = len(pd.date_range(start, end, freq=CANDLE, inclusive="left"))
    if total == 0:
        print("Dövr boşdur")
        return 1
    ratio = len(covered) / total
    ok = ratio >= MIN_UPTIME
    print(f"Şamlar: {total}  |  vaxtında emal: {len(covered)}  |  buraxılan: {total - len(covered)}")
    print(f"Uptime: {ratio:.2%} (hədd {MIN_UPTIME:.0%}) → {'KEÇDİ' if ok else 'UĞURSUZ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
