"""Kölgə portfel (agentlər) ↔ TrendEmaAtr paper — aylıq müqayisə (agent plan §5, A.7).

Hər iki tərəf EYNİ dövrdə, EYNİ düsturlarla ölçülür:
- PF: bağlanmış əməliyyatlar (oos_eval.profit_factor);
- DD: gündəlik MTM kapital nöqtələri (baseline.max_drawdown) — paper: paper_equity.csv,
  kölgə: shadow/equity.csv (hər ikisi səhər hesabatında yazılır);
- xalis: dövrün ilk və son kapital nöqtəsinin fərqi.
Qərar yalnız kölgə ≥ 30 bağlanmış əməliyyatda (və ya 24 ayda) verilir; o vaxta qədər GÖZLƏ.

Ticarətə TOXUNMUR: DB yalnız oxunur. Serverdə (cron, ayın 1-i):
    docker compose exec -T paper python /freqtrade/tools/shadow_compare.py --send
"""

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline import max_drawdown  # noqa: E402
from oos_eval import MAX_DRAWDOWN, MIN_PROFIT_FACTOR, MIN_TRADES, profit_factor  # noqa: E402

USER_DATA = Path("/freqtrade/user_data")
MAX_MONTHS = 24


def side_metrics(pnls: list[float], equity: pd.Series) -> dict:
    """pnls: dövrdə bağlanmış əməliyyatların mənfəəti; equity: dövrün gündəlik MTM kapitalı."""
    base = float(equity.iloc[0])
    net = float(equity.iloc[-1]) - base
    return {"n": len(pnls), "pf": profit_factor(pd.DataFrame({"profit_abs": pnls}, dtype=float)),
            "net": net, "net_pct": net / base * 100, "dd": max_drawdown(equity)}


def compare(shadow: dict, paper: dict, months: float) -> dict:
    checks = [
        {"name": f"PF > {MIN_PROFIT_FACTOR}", "ok": shadow["pf"] > MIN_PROFIT_FACTOR},
        {"name": f"MTM DD < {MAX_DRAWDOWN:.0%}", "ok": shadow["dd"] < MAX_DRAWDOWN},
        {"name": "xalis > 0", "ok": shadow["net"] > 0},
        {"name": "PF paper-dan yüksək", "ok": shadow["pf"] > paper["pf"]},
        {"name": "DD paper-dan aşağı", "ok": shadow["dd"] < paper["dd"]},
    ]
    if shadow["n"] < MIN_TRADES and months < MAX_MONTHS:
        status = "GÖZLƏ"
    else:
        status = "KEÇDİ" if all(c["ok"] for c in checks) else "KEÇMƏDİ"
    return {"status": status, "checks": checks}


def _fmt(m: dict) -> str:
    pf = "∞" if m["pf"] == float("inf") else f"{m['pf']:.2f}"
    return (f"əməliyyat {m['n']}, PF {pf}, xalis {m['net']:+.2f} USDT ({m['net_pct']:+.2f}%), "
            f"MTM DD {m['dd']:.1%}")


def build_message(shadow: dict, paper: dict, result: dict, start: pd.Timestamp, end: pd.Timestamp) -> str:
    lines = [f"🕶 KÖLGƏ ↔ TrendEmaAtr paper müqayisəsi ({start:%Y-%m-%d} → {end:%Y-%m-%d})", "",
             f"Agentlər (kölgə, icra olunmur): {_fmt(shadow)}",
             f"TrendEmaAtr (paper): {_fmt(paper)}", ""]
    if result["status"] == "GÖZLƏ":
        lines.append(f"Status: GÖZLƏ — kölgə əməliyyatları {shadow['n']} / {MIN_TRADES} "
                     f"(qərar ≥ {MIN_TRADES}-da və ya {MAX_MONTHS} ayda). Aralıq rəqəmlərə görə "
                     "prompt dəyişmək sınağı sıfırlayır.")
    else:
        lines.append(f"Status: {result['status']} (plan §5)")
    lines += [f"{'✅' if c['ok'] else '❌'} {c['name']}" for c in result["checks"]]
    return "\n".join(lines)


# --- mənbələr (serverdə, paper konteynerində) -----------------------------------

def load_equity(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    df = pd.read_csv(path, parse_dates=["date"])
    return pd.Series(df["equity"].values, index=pd.DatetimeIndex(df["date"]), dtype=float).sort_index()


def main() -> int:
    from freqtrade.data.btanalysis import load_trades_from_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data", type=Path, default=USER_DATA)
    parser.add_argument("--start", help="YYYY-MM-DD (default: hər iki tərəfin datası olan ilk gün)")
    parser.add_argument("--send", action="store_true", help="Telegram-a göndər")
    args = parser.parse_args()

    ud = args.user_data
    config = json.loads((ud / "config.paper.json").read_text())
    shadow_eq = load_equity(ud / "shadow" / "equity.csv")
    paper_eq = load_equity(ud / "paper_equity.csv")
    if shadow_eq.empty or paper_eq.empty:
        print("XƏTA: kapital tarixçəsi yoxdur (shadow/equity.csv və ya paper_equity.csv)", file=sys.stderr)
        return 2
    start = pd.Timestamp(args.start) if args.start else max(shadow_eq.index[0], paper_eq.index[0])
    end = min(shadow_eq.index[-1], paper_eq.index[-1])
    if end < start:
        print(f"XƏTA: ortaq dövr yoxdur (başlanğıc {start:%Y-%m-%d}, son {end:%Y-%m-%d})", file=sys.stderr)
        return 2
    shadow_eq, paper_eq = shadow_eq[start:end], paper_eq[start:end]

    # Bağlanma tarixi Bakı günü ilə; dövrün son günü daxil
    book = json.loads((ud / "shadow" / "book.json").read_text())
    def in_period(ts) -> bool:
        day = pd.Timestamp(ts).tz_convert("Asia/Baku").tz_localize(None).normalize()
        return start <= day <= end
    shadow_pnls = [t["pnl"] for t in book["trades"] if in_period(t["closed"])]
    trades = load_trades_from_db(config["db_url"])
    closed = trades[~trades["is_open"].astype(bool)] if not trades.empty else trades
    paper_pnls = [float(r.profit_abs) for r in closed.itertuples() if in_period(r.close_date)]

    shadow, paper = side_metrics(shadow_pnls, shadow_eq), side_metrics(paper_pnls, paper_eq)
    result = compare(shadow, paper, (end - start).days / 30.44)
    message = build_message(shadow, paper, result, start, end)
    print(message)
    if args.send:
        from paper_report import send_telegram

        send_telegram(message)
        print("Telegram: göndərildi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
