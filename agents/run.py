"""Gündəlik kölgə dövrü: faktlar → agentlər → supervayzer → kölgə portfel → jurnal + Telegram.

Qərarlar HEÇ VAXT icra olunmur. Bot-un DB-sinə, konfiqurasiyasına, strategiyasına heç nə yazılmır;
yazılan yeganə yer: user_data/shadow/ (book.json, decisions.csv, runs.jsonl).

Serverdə (cron 09:10 Bakı):
    docker compose run --rm agents python -m agents.run --send
Açarlar (.env): GROQ_API_KEY, LANGSMITH_API_KEY, FREQTRADE__TELEGRAM__TOKEN / CHAT_ID.

Məlum məhdudiyyət: girişin düşdüyü 4h şam stop üçün yoxlanmır (low girişdən əvvəl də ola bilər);
stop yoxlaması girişdən SONRA açılan şamlardan başlayır.
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
sys.path.insert(0, str(_ROOT))

from agents.prompts import PROMPT_VERSION  # noqa: E402
from agents.shadow import ShadowBook  # noqa: E402

BAKU = "Asia/Baku"
CONFIG = _ROOT / "user_data" / "config.paper.json"
STATE_DIR = _ROOT / "user_data" / "shadow"
COLUMNS = ["time", "prompt_version", "pair", "action", "confidence", "price", "outcome",
           "decision_ok", "agents_failed", "max_new", "rationale", "error"]
TELEGRAM_LIMIT = 4000


def h4_frame(rows: list) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["date"], unit="ms", utc=True)
    return df


def run_cycle(book: ShadowBook, graph, pairs: list[str], facts: dict, h4: dict,
              risk_facts: dict, news: list[str], now: pd.Timestamp) -> dict:
    """Əvvəl stoplar (agentlər aktual mövqeləri görsün), sonra qraf, sonra kölgə icra."""
    stops = book.check_stops(h4)
    positions = [{"pair": p.pair, "entry": p.entry, "stop": p.stop, "opened": p.opened}
                 for p in book.positions.values()]
    out = graph.invoke({"pairs": pairs, "facts": facts, "risk_facts": risk_facts, "news": news,
                        "positions": positions, "now": now.isoformat(), "reports": {}})
    d = out["decision"]
    events = {}
    if d["ok"]:
        prices = {p: facts[p]["price"] for p in pairs}
        atrs = {p: facts[p]["atr14"] for p in pairs}
        events = dict(book.apply(d["actions"], prices, atrs, now, d["max_new"]))
    return {"stops": stops, "reports": out["reports"], "decision": d, "events": events}


def _failed(result: dict) -> list[str]:
    return [n for n, r in result["reports"].items() if not r.get("ok")]


def decision_rows(result: dict, facts: dict, now: pd.Timestamp, version: str) -> list[dict]:
    d = result["decision"]
    details = {x["pair"]: x for x in d.get("details", [])}
    rows = []
    for pair, action in d["actions"].items():
        det = details.get(pair, {})
        rows.append({"time": now.isoformat(), "prompt_version": version, "pair": pair,
                     "action": action, "confidence": det.get("confidence"),
                     "price": facts[pair]["price"], "outcome": result["events"].get(pair, ""),
                     "decision_ok": d["ok"], "agents_failed": ",".join(_failed(result)),
                     "max_new": d["max_new"], "rationale": det.get("rationale", ""),
                     "error": d.get("error") or ""})
    return rows


def append_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


def already_ran(path: Path, now: pd.Timestamp) -> bool:
    """Bu Bakı günündə artıq qərar yazılıbmı (cron iki dəfə işləsə, kölgə iki dəfə alış etməsin)."""
    if not path.exists():
        return False
    times = pd.to_datetime(pd.read_csv(path, usecols=["time"])["time"], utc=True)
    today = now.tz_convert(BAKU).date()
    return bool((times.dt.tz_convert(BAKU).dt.date == today).any())


def _usdt(x: float) -> str:
    return f"{x:,.2f}".replace(",", " ")


def compose_message(result: dict, book: ShadowBook, facts: dict, now: pd.Timestamp) -> str:
    d = result["decision"]
    lines = [f"🕶 KÖLGƏ — icra olunmur ({now.tz_convert(BAKU):%Y-%m-%d} Bakı)",
             "Agentlərin qərarları yalnız simulyasiya olunur; paper bot-a təsir etmir.", ""]
    for name in _failed(result):
        lines.append(f"⚠️ {name} analitiki UĞURSUZ: {result['reports'][name].get('error')}")
    if d["ok"]:
        lines.append(f"🧑‍⚖️ Supervayzer: {d['summary']}")
        lines.append(f"Yeni mövqe limiti (risk): {d['max_new']}")
        for x in d.get("details", []):
            outcome = result["events"].get(x["pair"])
            tail = f" → {outcome}" if outcome else ""
            lines.append(f"• {x['pair']}: {x['action']} ({x['confidence']:.2f}){tail} — {x['rationale']}")
    else:
        lines.append(f"⛔ Supervayzer uğursuz ({d.get('error')}) — bütün cütlər GÖZLƏ.")
    for pair in result["stops"]:
        t = next(t for t in reversed(book.trades) if t["pair"] == pair)
        lines.append(f"🛑 {pair} stopla bağlandı: {t['exit']} ({_usdt(t['pnl'])} USDT)")
    lines += ["", f"Kölgə kapital (reallaşmış): {_usdt(book.equity)} USDT"]
    for p in book.positions.values():
        price = facts.get(p.pair, {}).get("price", p.entry)
        lines.append(f"  açıq {p.pair}: giriş {p.entry}, stop {p.stop:.6g}, "
                     f"cari nəticə {_usdt(p.amount * (price - p.entry))} USDT")
    lines.append(f"Bağlanmış kölgə əməliyyatları: {len(book.trades)} (qiymətləndirmə ≥ 30-da)")
    text = "\n".join(lines)
    return text if len(text) <= TELEGRAM_LIMIT else text[:TELEGRAM_LIMIT - 1] + "…"


# --- şəbəkə (yalnız serverdə) -------------------------------------------------------

def fetch_market(config: dict) -> tuple[dict, dict, dict]:
    import ccxt

    from agents.facts import risk_facts, technical_facts

    ex = ccxt.binance(config["exchange"].get("ccxt_config", {}))
    facts, h4s, d1s = {}, {}, {}
    for pair in config["exchange"]["pair_whitelist"]:
        d1 = h4_frame(ex.fetch_ohlcv(pair, "1d", limit=31))
        h4 = h4_frame(ex.fetch_ohlcv(pair, "4h", limit=300))
        facts[pair], h4s[pair], d1s[pair] = technical_facts(d1, h4), h4, d1
    return facts, h4s, risk_facts(d1s)


def make_llms(key: str, model: str) -> dict:
    from langchain_groq import ChatGroq

    def llm():
        return ChatGroq(api_key=key, model=model, temperature=0.2, reasoning_effort="low",
                        max_tokens=2500, max_retries=2, timeout=90)
    return {name: llm() for name in ("texniki", "xəbər", "risk", "supervayzer")}


def main() -> int:
    from market_brief import DEFAULT_MODEL, fetch_news
    from paper_report import send_telegram

    from agents.graph import build_graph

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    parser.add_argument("--send", action="store_true", help="Telegram-a göndər")
    parser.add_argument("--force", action="store_true", help="bu gün artıq işləyibsə də işlət")
    args = parser.parse_args()

    now = pd.Timestamp.now(tz="UTC").floor("s")
    decisions = args.state_dir / "decisions.csv"
    if already_ran(decisions, now) and not args.force:
        print("Bu gün artıq işləyib (decisions.csv). Təkrar üçün --force.")
        return 0
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        print("XƏTA: GROQ_API_KEY yoxdur", file=sys.stderr)
        return 2

    config = json.loads(args.config.read_text())
    facts, h4, rfacts = fetch_market(config)
    news = fetch_news(now)
    book_path = args.state_dir / "book.json"
    book = ShadowBook.load(book_path)
    graph = build_graph(make_llms(key, os.environ.get("GROQ_MODEL") or DEFAULT_MODEL))
    result = run_cycle(book, graph, list(facts), facts, h4, rfacts, news, now)

    book.save(book_path)
    append_rows(decisions, decision_rows(result, facts, now, PROMPT_VERSION))
    with (args.state_dir / "runs.jsonl").open("a", encoding="utf-8") as f:  # tam audit izi
        f.write(json.dumps({"time": now.isoformat(), "prompt_version": PROMPT_VERSION,
                            "facts": facts, "risk_facts": rfacts, "news": news, **result},
                           ensure_ascii=False, default=str) + "\n")

    message = compose_message(result, book, facts, now)
    print(message)
    if args.send:
        send_telegram(message)
        print("Telegram: göndərildi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
