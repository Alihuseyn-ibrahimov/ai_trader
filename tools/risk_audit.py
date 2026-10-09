"""Backtest nəticəsinin risk auditi — risk qaydaları real əməliyyatlarda pozulubmu?

Freqtrade-in backtest JSON nəticəsini oxuyur və hər əməliyyatı yoxlayır.
Mətnə/hesabata yox, əməliyyat datasına baxır (CLAUDE.md: mənbədən yoxla).

Yoxlamalar:
- risk_per_trade: stopda planlaşdırılan itki (komissiya daxil) / girişdəki kapital <= limit
- max_open_trades: eyni anda açıq mövqe sayı <= limit
- floor: reallaşmış kapital heç vaxt alt xəttin altına düşmür
Əlavə məlumat: faktiki ən pis itki (stopdan boşluqla keçmə), çıxış səbəbləri.

Konteynerdə işlətmə (ai_trader qovluğundan, backtest-dən sonra):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/risk_audit.py RiskSmokeTest
"""

import json
import sys
from pathlib import Path

import pandas as pd

# signals/ paketi tools/-un yanındadır (konteynerdə /freqtrade/signals)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from signals.tags import parse_stop_dist  # noqa: E402

TOLERANCE = 1e-6
CONFIG = Path("/freqtrade/user_data/config.json")
RESULTS_DIR = Path("/freqtrade/user_data/backtest_results")


def _max_concurrent(trades: pd.DataFrame) -> int:
    # Eyni anda bağlanan və açılan mövqe üst-üstə düşmür: bağlanma əvvəl sayılır
    events = [(t, 1) for t in trades["open_date"]] + [(t, -1) for t in trades["close_date"]]
    events.sort(key=lambda e: (e[0], e[1]))
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def audit_trades(
    trades: pd.DataFrame,
    starting_balance: float,
    risk_pct: float,
    floor_ratio: float,
    max_open_trades: int,
) -> dict:
    floor = starting_balance * floor_ratio
    if trades.empty:
        return {"n_trades": 0, "checks": {"has_trades": False}}

    trades = trades.sort_values("open_date").reset_index(drop=True)

    equity_at_open = [
        starting_balance + trades.loc[trades["close_date"] <= row.open_date, "profit_abs"].sum()
        for row in trades.itertuples()
    ]
    # Planlaşdırılan stop: tag-da ATR məsafəsi varsa ondan, yoxdursa Freqtrade-in
    # ilkin stopundan (custom_stoploss istifadə edəndə o yalnız sabit backstop-dur)
    tags = trades["enter_tag"] if "enter_tag" in trades else pd.Series([None] * len(trades))
    dist = tags.map(parse_stop_dist)
    stop = (trades["open_rate"] - dist).where(dist.notna(), trades["initial_stop_loss_abs"])
    planned_loss = (
        trades["amount"] * (trades["open_rate"] - stop)
        + trades["amount"] * trades["open_rate"] * trades["fee_open"]
        + trades["amount"] * stop * trades["fee_close"]
    )
    eq = pd.Series(equity_at_open)
    planned_ratio = planned_loss / eq
    actual_loss_ratio = (-trades["profit_abs"]).clip(lower=0) / eq

    by_close = trades.sort_values("close_date")
    equity_curve = starting_balance + by_close["profit_abs"].cumsum()
    min_equity = min(starting_balance, float(equity_curve.min()))
    max_concurrent = _max_concurrent(trades)

    return {
        "n_trades": len(trades),
        "equity_at_open": equity_at_open,
        "max_planned_risk": float(planned_ratio.max()),
        "worst_actual_loss": float(actual_loss_ratio.max()),
        "max_concurrent": max_concurrent,
        "min_equity": min_equity,
        "floor": floor,
        "max_stake_share": float((trades["stake_amount"] / eq).max()),
        "exit_reasons": trades["exit_reason"].value_counts().to_dict(),
        "checks": {
            "has_trades": True,
            "risk_per_trade": bool(planned_ratio.max() <= risk_pct + TOLERANCE),
            "max_open_trades": max_concurrent <= max_open_trades,
            "floor": min_equity > floor,
        },
    }


def main(strategy: str) -> int:
    from freqtrade.data.btanalysis import load_backtest_data, load_backtest_stats

    risk = json.loads(CONFIG.read_text())["ai_risk"]
    stats = load_backtest_stats(RESULTS_DIR)["strategy"][strategy]
    trades = load_backtest_data(RESULTS_DIR, strategy=strategy)
    r = audit_trades(
        trades,
        starting_balance=float(stats["starting_balance"]),
        risk_pct=risk["risk_per_trade"],
        floor_ratio=risk["floor_ratio"],
        max_open_trades=risk["max_open_trades"],
    )

    print(f"Strategiya: {strategy}  |  əməliyyat sayı: {r['n_trades']}")
    if not r["checks"]["has_trades"]:
        print("XƏTA: əməliyyat yoxdur — audit mənasızdır")
        return 1
    print(f"Ən böyük planlaşdırılan risk / kapital: {r['max_planned_risk']:.3%} (limit {risk['risk_per_trade']:.2%})")
    print(f"Ən pis faktiki itki / kapital:          {r['worst_actual_loss']:.3%}")
    print(f"Ən böyük stake / kapital:               {r['max_stake_share']:.1%}")
    print(f"Eyni anda maks. açıq mövqe:             {r['max_concurrent']} (limit {risk['max_open_trades']})")
    print(f"Minimum reallaşmış kapital:             {r['min_equity']:.2f} (alt xətt {r['floor']:.2f})")
    print(f"Çıxış səbəbləri: {r['exit_reasons']}")
    print()
    failed = [name for name, ok in r["checks"].items() if not ok]
    for name, ok in r["checks"].items():
        print(f"  {'KEÇDİ ' if ok else 'UĞURSUZ'}  {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("İstifadə: risk_audit.py <StrategiyaAdı>")
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
