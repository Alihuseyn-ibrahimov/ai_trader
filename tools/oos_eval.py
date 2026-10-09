"""OOS qiymətləndirməsi və Go / No-Go qərarı (Phase 0.6).

Yalnız OOS backtest-indən SONRA, bir dəfə işlədilir. Meyarlar task_plan.md-də OOS-dan
ƏVVƏL sabitlənib və burada kodlaşdırılıb — nəticəyə baxıb dəyişdirilmir.

Hesablama:
- Xalis gəlir: bağlanmış əməliyyatların mənfəəti − 14% vergi (hər təqvim ili ayrıca,
  yalnız müsbət ildə; zərər növbəti ilə keçirilmir — ehtiyatlı fərziyyə)
- Drawdown: gündəlik mark-to-market kapital üzrə (açıq mövqelərin cari zərəri daxil),
  buy & hold baseline ilə eyni üsul
- Baseline: 50/50 BTC+ETH buy & hold, eyni dövr, eyni komissiya və vergi

Konteynerdə işlətmə (ai_trader qovluğundan, OOS backtest-dən sonra):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/oos_eval.py TrendEmaAtr --is-profit-factor 3.17
"""

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from baseline import FEE, TAX, max_drawdown, net_return, portfolio_equity  # noqa: E402
from data_quality import slice_period  # noqa: E402

OOS_START = "2025-01-01"
OOS_END = "2026-09-30"
DATA_DIR = Path("/freqtrade/user_data/data/binance")
RESULTS_DIR = Path("/freqtrade/user_data/backtest_results")

# Meyarlar (task_plan.md, OOS-dan əvvəl sabitlənib)
MIN_TRADES = 30
MAX_DRAWDOWN = 0.20
MIN_PROFIT_FACTOR = 1.2
BASELINE_SHARE = 0.7
BASELINE_DD_SHARE = 0.5
IS_PF_SHARE = 0.5


def yearly_tax(trades: pd.DataFrame, rate: float) -> float:
    if trades.empty:
        return 0.0
    by_year = trades.groupby(trades["close_date"].dt.year)["profit_abs"].sum()
    return float((by_year.clip(lower=0) * rate).sum())


def profit_factor(trades: pd.DataFrame) -> float:
    if trades.empty:
        return 0.0
    wins = trades.loc[trades["profit_abs"] > 0, "profit_abs"].sum()
    losses = -trades.loc[trades["profit_abs"] < 0, "profit_abs"].sum()
    if losses == 0:
        return math.inf if wins > 0 else 0.0
    return float(wins / losses)


def mtm_equity(trades: pd.DataFrame, prices: dict, start_balance: float, start: str,
               end: str) -> pd.Series:
    """Hər gün sonu: başlanğıc + reallaşmış mənfəət + açıq mövqelərin cari dəyəri.

    Gün sonu qiyməti = həmin günün 1d şamının bağlanışı (şam tarixi t − 1 gün).
    """
    times = pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"), freq="1D")
    close_at = {p: df.set_index("date")["close"] for p, df in prices.items()}
    values = [start_balance]
    for t in times[1:]:
        closed = trades["close_date"] <= t
        equity = start_balance + trades.loc[closed, "profit_abs"].sum()
        open_now = trades[(trades["open_date"] < t) & ~closed]
        for row in open_now.itertuples():
            candle = t - pd.Timedelta(days=1)
            if candle not in close_at[row.pair].index:
                raise ValueError(f"{row.pair} üçün {candle:%Y-%m-%d} gündəlik qiyməti yoxdur")
            price = close_at[row.pair][candle]
            equity += row.amount * price * (1 - row.fee_close) - row.stake_amount * (1 + row.fee_open)
        values.append(float(equity))
    return pd.Series(values, index=times)


def evaluate(metrics: dict, bh_net_return: float, bh_max_drawdown: float,
             is_profit_factor: float) -> dict:
    n, dd = metrics["n_trades"], metrics["max_drawdown"]
    pf, net = metrics["profit_factor"], metrics["net_return"]
    beats_baseline = net > bh_net_return or (
        bh_net_return > 0
        and net >= BASELINE_SHARE * bh_net_return
        and dd <= BASELINE_DD_SHARE * bh_max_drawdown
    )
    criteria = {
        "1_trades": n >= MIN_TRADES,
        "2_drawdown": dd < MAX_DRAWDOWN,
        "3_profit_factor": pf > MIN_PROFIT_FACTOR,
        "4_vs_baseline": bool(beats_baseline),
        "5_is_vs_oos": pf >= IS_PF_SHARE * is_profit_factor,
        "6_positive": net > 0,
    }
    return {"criteria": criteria, "go": all(criteria.values())}


def main() -> int:
    from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats

    parser = argparse.ArgumentParser()
    parser.add_argument("strategy")
    parser.add_argument("--is-profit-factor", type=float, required=True)
    args = parser.parse_args()

    stats = load_backtest_stats(RESULTS_DIR)["strategy"][args.strategy]
    trades = load_backtest_data(RESULTS_DIR, strategy=args.strategy)
    start_balance = float(stats["starting_balance"])
    lo, hi = pd.Timestamp(OOS_START, tz="UTC"), pd.Timestamp(OOS_END, tz="UTC")
    if trades.empty or trades["open_date"].min() < lo or trades["close_date"].max() > hi:
        print(f"XƏTA: son backtest OOS dövründə deyil [{OOS_START}, {OOS_END}) — "
              "əvvəlcə --timerange 20250101-20260930 ilə backtest işlət")
        return 2

    pairs = sorted(trades["pair"].unique())
    prices = {p: pd.read_feather(DATA_DIR / f"{p.replace('/', '_')}-1d.feather") for p in pairs}
    eq = mtm_equity(trades, prices, start_balance, OOS_START, OOS_END)
    gross = float(trades["profit_abs"].sum())
    tax = yearly_tax(trades, TAX)
    metrics = {
        "n_trades": len(trades),
        "max_drawdown": max_drawdown(eq),
        "profit_factor": profit_factor(trades),
        "net_return": (gross - tax) / start_balance,
    }

    bh = [slice_period(pd.read_feather(DATA_DIR / f"{p}-1d.feather"), OOS_START, OOS_END)
          for p in ("BTC_USDT", "ETH_USDT")]
    bh_eq = portfolio_equity(bh, [0.5, 0.5])
    bh_net, bh_dd = net_return(float(bh_eq.iloc[-1]), FEE, TAX), max_drawdown(bh_eq)
    r = evaluate(metrics, bh_net, bh_dd, args.is_profit_factor)

    print(f"OOS [{OOS_START}, {OOS_END}) — {args.strategy}\n")
    print("| Metrik | Strategiya | Baseline 50/50 B&H |")
    print("|---|---|---|")
    print(f"| Əməliyyat | {metrics['n_trades']} | — |")
    print(f"| Brüt mənfəət | {gross:+.2f} USDT ({gross / start_balance:+.2%}) | — |")
    print(f"| Vergi (14%, illik) | {tax:.2f} USDT | — |")
    print(f"| Xalis gəlir | {metrics['net_return']:+.2%} | {bh_net:+.2%} |")
    print(f"| Maks. drawdown (gündəlik MTM) | {metrics['max_drawdown']:.2%} | {bh_dd:.2%} |")
    print(f"| Profit factor | {metrics['profit_factor']:.2f} | — (IS: {args.is_profit_factor:.2f}) |")
    print()
    labels = {
        "1_trades": f"Əməliyyat sayı ≥ {MIN_TRADES}",
        "2_drawdown": f"Maks. drawdown < {MAX_DRAWDOWN:.0%}",
        "3_profit_factor": f"Profit factor > {MIN_PROFIT_FACTOR}",
        "4_vs_baseline": "Baseline-dan yaxşı (və ya ≥70% gəlir, ≤½ DD)",
        "5_is_vs_oos": f"OOS PF ≥ {IS_PF_SHARE:.0%} × IS PF ({IS_PF_SHARE * args.is_profit_factor:.2f})",
        "6_positive": "Xalis gəlir > 0",
    }
    for key, ok in r["criteria"].items():
        print(f"  {'KEÇDİ  ' if ok else 'UĞURSUZ'}  {key[0]}. {labels[key]}")
    print(f"\nQƏRAR: {'GO' if r['go'] else 'NO-GO'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
