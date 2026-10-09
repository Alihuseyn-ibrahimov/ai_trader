"""Faza 1 — yekun (və aylıq) qiymətləndirmə: plan §4 meyarları 1–4.

Meyar 5 → `risk_audit.py --db`, 6 → `parity.py`, 7 → `uptime.py`. Hədlər sınaqdan
ƏVVƏL sabitlənib (task_plan.md §4), nəticəyə baxıb dəyişdirilmir. Aylıq işlətmə
yalnız məlumat üçündür — qərar n ≥ 30 və ya 24 ayda verilir.

Əvvəlcə gündəlik qiymətlər lazımdır (MTM drawdown üçün):
    docker compose run --rm freqtrade download-data --config user_data/config.paper.json --timeframes 1d --days 800
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/paper_eval.py --start 2026-11-01
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline import TAX, max_drawdown  # noqa: E402
from oos_eval import (  # noqa: E402
    MAX_DRAWDOWN, MIN_PROFIT_FACTOR, MIN_TRADES, gross_wins_losses, mtm_equity, profit_factor,
    yearly_tax,
)

CONFIG = Path("/freqtrade/user_data/config.paper.json")
DATA_DIR = Path("/freqtrade/user_data/data/binance")


def evaluate_paper(metrics: dict) -> dict:
    criteria = {
        "1_trades": metrics["n_trades"] >= MIN_TRADES,
        "2_drawdown": metrics["max_drawdown"] < MAX_DRAWDOWN,
        "3_profit_factor": metrics["profit_factor"] > MIN_PROFIT_FACTOR,
        "4_positive": metrics["net_return"] > 0,
    }
    return {"criteria": criteria, "pass": all(criteria.values())}


def main() -> int:
    from freqtrade.data.btanalysis import load_trades_from_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--start", required=True, help="T0")
    parser.add_argument("--end", default=None, help="default: bu gün (UTC)")
    parser.add_argument("--strategy", default="TrendEmaAtr")
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    start_balance = float(config["dry_run_wallet"])
    trades = load_trades_from_db(config["db_url"], strategy=args.strategy)
    trades = trades[trades["open_date"] >= pd.Timestamp(args.start, tz="UTC")]
    closed = trades[~trades["is_open"].astype(bool)]
    end = args.end or pd.Timestamp.now(tz="UTC").normalize().strftime("%Y-%m-%d")
    if pd.Timestamp(end) <= pd.Timestamp(args.start):
        print(f"XƏTA: dövr boşdur [{args.start}, {end}) — --start T0 olmalıdır, bu gündən əvvəl")
        return 2

    prices = {p: pd.read_feather(DATA_DIR / f"{p.replace('/', '_')}-1d.feather")
              for p in sorted(trades["pair"].unique())}
    eq = mtm_equity(trades, prices, start_balance, args.start, end)
    gross = float(closed["profit_abs"].sum())
    tax = yearly_tax(closed, TAX)
    metrics = {
        "n_trades": len(closed),
        "max_drawdown": max_drawdown(eq),
        "profit_factor": profit_factor(closed),
        "net_return": (gross - tax) / start_balance,
    }
    wins, losses = gross_wins_losses(closed)
    r = evaluate_paper(metrics)

    print(f"PAPER [{args.start}, {end}) — {args.strategy} — açıq mövqe: {int(trades['is_open'].sum())}\n")
    print(f"| Bağlanmış əməliyyat | {metrics['n_trades']} |")
    print(f"| Brüt mənfəət | {gross:+.2f} USDT ({gross / start_balance:+.2%}) |")
    print(f"| Vergi (14%, illik) | {tax:.2f} USDT |")
    print(f"| Xalis gəlir | {metrics['net_return']:+.2%} |")
    print(f"| Maks. drawdown (gündəlik MTM) | {metrics['max_drawdown']:.2%} |")
    print(f"| Profit factor | {metrics['profit_factor']:.2f} |")
    print(f"| Qazanc / itki cəmi | {wins:.2f} / {losses:.2f} USDT |\n")
    labels = {
        "1_trades": f"Bağlanmış əməliyyat ≥ {MIN_TRADES}",
        "2_drawdown": f"Maks. drawdown < {MAX_DRAWDOWN:.0%}",
        "3_profit_factor": f"Profit factor > {MIN_PROFIT_FACTOR}",
        "4_positive": "Xalis gəlir > 0",
    }
    for key, ok in r["criteria"].items():
        print(f"  {'KEÇDİ  ' if ok else 'UĞURSUZ'}  {key[0]}. {labels[key]}")
    print("\nMeyar 5–7 ayrıca: risk_audit.py --db, parity.py, uptime.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
