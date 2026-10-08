"""Tarixi OHLCV datasının keyfiyyət yoxlaması (Phase 0.2).

Freqtrade-in yüklədiyi feather fayllarını oxuyur və bunları sayır:
boşluqlar (çatmayan şamlar), dublikatlar, OHLC məntiq pozuntuları, sıfır həcm.

Konteynerdə işlətmə (ai_trader qovluğundan):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/data_quality.py
"""

import sys
from pathlib import Path

import pandas as pd

TIMEFRAMES = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "1d": pd.Timedelta(days=1)}

# Faza 0 dövrü: IS + OOS. Yarımaçıq interval [başlanğıc, son) — Freqtrade
# `--timerange 20230101-20260930` ilə eyni.
PERIOD_START = "2023-01-01"
PERIOD_END = "2026-09-30"

DATA_DIR = Path("/freqtrade/user_data/data/binance")
MAX_GAPS_SHOWN = 30


def _step(timeframe: str) -> pd.Timedelta:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Naməlum timeframe: {timeframe!r}")
    return TIMEFRAMES[timeframe]


def slice_period(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """[start, end) aralığındakı şamlar (son tarix xaric)."""
    lo = pd.Timestamp(start, tz="UTC")
    hi = pd.Timestamp(end, tz="UTC")
    return df[(df["date"] >= lo) & (df["date"] < hi)].reset_index(drop=True)


def find_gaps(df: pd.DataFrame, timeframe: str) -> list[tuple[pd.Timestamp, int]]:
    """Hər boşluq üçün (ilk çatmayan şamın vaxtı, çatmayan şam sayı)."""
    step = _step(timeframe)
    dates = df["date"].drop_duplicates().sort_values().reset_index(drop=True)
    gaps = []
    for prev, cur in zip(dates[:-1], dates[1:]):
        missing = int((cur - prev) / step) - 1
        if missing > 0:
            gaps.append((prev + step, missing))
    return gaps


def count_duplicates(df: pd.DataFrame) -> int:
    return int(df["date"].duplicated().sum())


def ohlc_violations(df: pd.DataFrame) -> int:
    """high/low açılış-bağlanışı əhatə etmir və ya qiymət <= 0 olan şamlar."""
    bad = (
        (df["high"] < df[["open", "close"]].max(axis=1))
        | (df["low"] > df[["open", "close"]].min(axis=1))
        | (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    return int(bad.sum())


def zero_volume(df: pd.DataFrame) -> int:
    return int((df["volume"] <= 0).sum())


def check_file(path: Path, timeframe: str) -> dict:
    df = slice_period(pd.read_feather(path), PERIOD_START, PERIOD_END)
    step = _step(timeframe)
    expected = int((pd.Timestamp(PERIOD_END) - pd.Timestamp(PERIOD_START)) / step)
    return {
        "file": path.name,
        "rows": len(df),
        "expected": expected,
        "first": df["date"].min(),
        "last": df["date"].max(),
        "gaps": find_gaps(df, timeframe),
        "duplicates": count_duplicates(df),
        "ohlc_bad": ohlc_violations(df),
        "zero_volume": zero_volume(df),
    }


def main(data_dir: Path = DATA_DIR) -> int:
    files = sorted(data_dir.glob("*.feather"))
    if not files:
        print(f"XƏTA: {data_dir} qovluğunda feather faylı yoxdur")
        return 1

    print(f"Dövr: [{PERIOD_START}, {PERIOD_END})\n")
    print("| Fayl | Şam | Gözlənilən | Çatmır | Boşluq sayı | Dublikat | OHLC xətası | Sıfır həcm | İlk | Son |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    results = []
    for path in files:
        timeframe = path.stem.rsplit("-", 1)[-1]
        if timeframe not in TIMEFRAMES:
            continue
        r = check_file(path, timeframe)
        results.append(r)
        missing = sum(n for _, n in r["gaps"])
        print(
            f"| {r['file']} | {r['rows']} | {r['expected']} | {r['expected'] - r['rows']} "
            f"| {len(r['gaps'])} ({missing} şam) | {r['duplicates']} | {r['ohlc_bad']} "
            f"| {r['zero_volume']} | {r['first']:%Y-%m-%d %H:%M} | {r['last']:%Y-%m-%d %H:%M} |"
        )

    for r in results:
        if not r["gaps"]:
            continue
        print(f"\nBoşluqlar — {r['file']}:")
        for start, n in r["gaps"][:MAX_GAPS_SHOWN]:
            print(f"  {start:%Y-%m-%d %H:%M} UTC  — {n} şam")
        if len(r["gaps"]) > MAX_GAPS_SHOWN:
            print(f"  ... və daha {len(r['gaps']) - MAX_GAPS_SHOWN} boşluq")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR))
