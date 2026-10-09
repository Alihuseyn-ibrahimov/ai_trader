"""Faza 1, meyar 6 — paper ↔ backtest uyğunluğu.

Sual: backtest real vaxtda olanı düzgün təqlid edirmi? Eyni dövr və eyni
konfiqurasiya ilə backtest işlədilir; paper əməliyyatları ilə tutuşdurulur.
Uyğunluq: eyni cüt, açılış vaxtı fərqi ≤ 1 şam (4h). Hər əməliyyat ən çox bir dəfə
istifadə olunur. Nisbət = uyğun / (paper + backtest − uyğun). Hədd ≥ 90% (plan §4).

İşlətmə (əvvəlcə: backtesting --config user_data/config.paper.json --timerange <T0>-<bu gün> --export trades):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/parity.py --start 2026-11-01
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

CONFIG = Path("/freqtrade/user_data/config.paper.json")
RESULTS_DIR = Path("/freqtrade/user_data/backtest_results")
TOLERANCE = pd.Timedelta(hours=4)
MIN_PARITY = 0.90


def match_trades(paper: pd.DataFrame, backtest: pd.DataFrame,
                 tolerance: pd.Timedelta = TOLERANCE) -> dict:
    used: set[int] = set()
    matched = 0
    bt = backtest.reset_index(drop=True)
    rows = [] if paper.empty or bt.empty else paper.sort_values("open_date").itertuples()
    for row in rows:
        cands = bt[(bt["pair"] == row.pair) & ~bt.index.isin(used)]
        if cands.empty:
            continue
        diff = (cands["open_date"] - row.open_date).abs()
        best = diff.idxmin()
        if diff[best] <= tolerance:
            used.add(best)
            matched += 1
    n_p, n_b = len(paper), len(backtest)
    union = n_p + n_b - matched
    return {
        "matched": matched,
        "n_paper": n_p,
        "n_backtest": n_b,
        "only_paper": n_p - matched,
        "only_backtest": n_b - matched,
        "ratio": matched / union if union else None,
    }


def main() -> int:
    from freqtrade.data.btanalysis import load_backtest_data, load_trades_from_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--start", required=True, help="T0 (paper sınağının rəsmi başlanğıcı)")
    parser.add_argument("--strategy", default="TrendEmaAtr")
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    lo = pd.Timestamp(args.start, tz="UTC")
    paper = load_trades_from_db(config["db_url"], strategy=args.strategy)
    backtest = load_backtest_data(RESULTS_DIR, strategy=args.strategy)
    paper = paper[paper["open_date"] >= lo]
    backtest = backtest[backtest["open_date"] >= lo]
    if not backtest.empty and not paper.empty and backtest["open_date"].max() < paper["open_date"].max() - TOLERANCE:
        print("XƏBƏRDARLIQ: son backtest paper dövrünün sonunu əhatə etmir — --timerange-i yoxla")

    r = match_trades(paper, backtest)
    print(f"Paper: {r['n_paper']}  |  Backtest: {r['n_backtest']}  |  Uyğun: {r['matched']}")
    print(f"Yalnız paper-də: {r['only_paper']}  |  Yalnız backtest-də: {r['only_backtest']}")
    if r["ratio"] is None:
        print("Əməliyyat yoxdur — uyğunluq hesablanmır")
        return 1
    ok = r["ratio"] >= MIN_PARITY
    print(f"Uyğunluq: {r['ratio']:.1%} (hədd {MIN_PARITY:.0%}) → {'KEÇDİ' if ok else 'UĞURSUZ'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
