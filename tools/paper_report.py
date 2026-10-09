"""Faza 1 — gündəlik paper trading hesabatı (Azərbaycan dilində, Telegram).

Mənbə: bot-un sqlite DB-si (yeganə həqiqət mənbəyi) + açıq mövqelər üçün cari qiymət.
Hər işləmədə günün kapitalı `paper_equity.csv`-yə yazılır — gündəlik MTM tarixçəsi
(drawdown və plan §5 dayandırma qaydaları bundan hesablanır).

Serverdə (gündəlik cron):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/paper_report.py --send
Göndərmədən yoxlamaq üçün `--send` olmadan işlət (mətn ekrana çıxır).
Telegram token və chat_id yalnız mühit dəyişənlərindən: FREQTRADE__TELEGRAM__TOKEN,
FREQTRADE__TELEGRAM__CHAT_ID (konfiqurasiyada boşdur).
"""

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline import max_drawdown  # noqa: E402
from oos_eval import MAX_DRAWDOWN, MIN_TRADES, profit_factor  # noqa: E402
from signals.tags import parse_stop_dist  # noqa: E402

CONFIG = Path("/freqtrade/user_data/config.paper.json")
HISTORY = Path("/freqtrade/user_data/paper_equity.csv")
BAKU = "Asia/Baku"


def current_equity(trades: pd.DataFrame, prices: dict, start_balance: float) -> float:
    """Başlanğıc + reallaşmış mənfəət + açıq mövqelərin cari dəyəri (oos_eval.mtm_equity ilə eyni düstur)."""
    if trades.empty:
        return float(start_balance)
    closed = trades[~trades["is_open"].astype(bool)]
    equity = start_balance + float(closed["profit_abs"].sum())
    for row in trades[trades["is_open"].astype(bool)].itertuples():
        price = prices[row.pair]  # qiymət yoxdursa — səssiz səhv yox, xəta
        equity += row.amount * price * (1 - row.fee_close) - row.stake_amount * (1 + row.fee_open)
    return float(equity)


def load_history(path: Path) -> pd.Series:
    if not path.exists():
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    df = pd.read_csv(path, parse_dates=["date"])
    return pd.Series(df["equity"].values, index=pd.DatetimeIndex(df["date"]), dtype=float)


def record_snapshot(path: Path, day: pd.Timestamp, equity: float) -> None:
    """Gündə bir sətir; eyni gün yenidən yazılırsa köhnə dəyər əvəz olunur."""
    key = day.strftime("%Y-%m-%d")
    rows = {}
    if path.exists():
        old = pd.read_csv(path, dtype={"date": str})
        rows = dict(zip(old["date"], old["equity"]))
    rows[key] = round(float(equity), 2)
    out = pd.DataFrame(sorted(rows.items()), columns=["date", "equity"])
    out.to_csv(path, index=False)


def report_state(trades: pd.DataFrame, prices: dict, start_balance: float, floor_ratio: float,
                 history: pd.Series, equity: float) -> dict:
    """history — bu gündən ƏVVƏLKİ günlərin kapitalı."""
    curve = pd.Series([start_balance, *history.tolist(), equity], dtype=float)
    floor = start_balance * floor_ratio
    closed = trades[~trades["is_open"].astype(bool)] if not trades.empty else trades
    open_ = trades[trades["is_open"].astype(bool)] if not trades.empty else trades
    drawdown = max_drawdown(curve)

    positions = []
    for row in open_.itertuples():
        dist = parse_stop_dist(row.enter_tag)
        price = prices[row.pair]
        positions.append({
            "pair": row.pair,
            "open_rate": row.open_rate,
            "price": price,
            "change": price / row.open_rate - 1,
            "stop": row.open_rate - dist if dist is not None else None,
        })

    alerts = []
    if drawdown >= MAX_DRAWDOWN:
        alerts.append("drawdown_stop")
    if equity <= floor:
        alerts.append("floor")
    if len(closed) >= MIN_TRADES:
        alerts.append("final_eval")

    return {
        "equity": equity,
        "start_balance": start_balance,
        "day_pnl": equity - (history.iloc[-1] if len(history) else start_balance),
        "drawdown": drawdown,
        "floor": floor,
        "n_closed": len(closed),
        "wins": int((closed["profit_abs"] > 0).sum()) if len(closed) else 0,
        "losses": int((closed["profit_abs"] < 0).sum()) if len(closed) else 0,
        "profit_factor": profit_factor(closed) if len(closed) else None,
        "positions": positions,
        "alerts": alerts,
    }


def _usdt(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ")


def _price(x: float) -> str:
    return f"{x:.2f}" if x >= 100 else f"{x:.4f}" if x >= 1 else f"{x:.6f}"


ALERT_TEXT = {
    "drawdown_stop": "⛔ Drawdown 20%-ə çatdı. Plan §5: botu DAYANDIR, nəticə NO-GO.",
    "floor": "⛔ Kapital alt xəttə çatdı. Plan §5: botu DAYANDIR, nəticə NO-GO.",
    "final_eval": "✅ 30 bağlanmış əməliyyat toplandı — yekun qiymətləndirmə vaxtıdır (Phase 1.6).",
}


def build_report(s: dict, now: pd.Timestamp) -> str:
    local = now.tz_convert(BAKU)
    total = s["equity"] / s["start_balance"] - 1
    pf = "—" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
    lines = [
        f"📊 AI Trader — paper hesabat ({local:%Y-%m-%d %H:%M} Bakı)",
        "",
        f"Kapital: {_usdt(s['equity'])} USDT ({total:+.2%} başlanğıcdan)",
        f"Son gün: {s['day_pnl']:+,.2f} USDT".replace(",", " "),
        f"Drawdown (pikdən): {s['drawdown']:.2%} — dayandırma həddi {MAX_DRAWDOWN:.0%}",
        f"Alt xətt: {_usdt(s['floor'])} USDT — məsafə {_usdt(s['equity'] - s['floor'])} USDT",
        f"Bağlanmış əməliyyat: {s['n_closed']}/{MIN_TRADES} "
        f"({s['wins']} qazanc, {s['losses']} itki), PF {pf}",
        "",
        f"Açıq mövqelər ({len(s['positions'])}):",
    ]
    for p in s["positions"]:
        stop = "—" if p["stop"] is None else _price(p["stop"])
        lines.append(f"  • {p['pair']}: giriş {_price(p['open_rate'])}, indi {_price(p['price'])} "
                     f"({p['change']:+.1%}), stop {stop}")
    if not s["positions"]:
        lines.append("  yoxdur")
    if s["alerts"]:
        lines.append("")
        lines.extend(ALERT_TEXT[a] for a in s["alerts"])
    return "\n".join(lines)


def telegram_payload(token: str, chat_id: str, text: str) -> tuple[str, dict]:
    return f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat_id, "text": text}


def send_telegram(text: str) -> None:
    token = os.environ.get("FREQTRADE__TELEGRAM__TOKEN", "")
    chat_id = os.environ.get("FREQTRADE__TELEGRAM__CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("FREQTRADE__TELEGRAM__TOKEN / CHAT_ID mühit dəyişənləri yoxdur")
    url, body = telegram_payload(token, chat_id, text)
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (sabit https ünvanı)
        if resp.status != 200:
            raise RuntimeError(f"Telegram cavabı: HTTP {resp.status}")


def fetch_prices(config: dict, pairs: list[str]) -> dict:
    import ccxt

    ex = ccxt.binance(config["exchange"].get("ccxt_config", {}))
    return {p: float(ex.fetch_ticker(p)["last"]) for p in pairs}


def main() -> int:
    from freqtrade.data.btanalysis import load_trades_from_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--history", type=Path, default=HISTORY)
    parser.add_argument("--send", action="store_true", help="Telegram-a göndər")
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    start = float(config["dry_run_wallet"])
    trades = load_trades_from_db(config["db_url"])
    open_pairs = sorted(trades.loc[trades["is_open"].astype(bool), "pair"].unique()) if not trades.empty else []
    prices = fetch_prices(config, open_pairs)

    now = pd.Timestamp.now(tz="UTC")
    today = now.tz_convert(BAKU).normalize().tz_localize(None)
    history = load_history(args.history)
    history = history[history.index < today]
    equity = current_equity(trades, prices, start)
    state = report_state(trades, prices, start, config["ai_risk"]["floor_ratio"], history, equity)
    record_snapshot(args.history, today, equity)

    text = build_report(state, now)
    print(text)
    if args.send:
        send_telegram(text)
        print("\nTelegram: göndərildi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
