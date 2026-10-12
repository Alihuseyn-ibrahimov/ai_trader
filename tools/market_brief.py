"""Gündəlik AI bazar icmalı → Telegram (Azərbaycan dilində). Plan:
.planning/2026-10-12-ai-trader-market-brief/task_plan.md

Pozulmaz qaydalar:
- Ticarətə TOXUNMUR: bot-un DB-sinə, konfiqurasiyasına, strategiyasına heç nə yazmır.
- Rəqəmləri kod hesablayır (Binance datası). LLM yalnız verilən faktlardan mətn yazır;
  mətndəki hər rəqəm faktlarda/başlıqlarda olmalıdır, yoxsa 1 düzəliş cəhdi, sonra imtina.
- LLM alınmasa, faktlar cədvəli yenə göndərilir və uğursuzluq AÇIQ yazılır.

Serverdə (cron, hesabatdan sonra):
    docker compose exec -T paper python /freqtrade/tools/market_brief.py --send
Açar: GROQ_API_KEY (yalnız serverdəki .env). Model: GROQ_MODEL (default llama-3.3-70b-versatile).
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baseline import annual_volatility  # noqa: E402
from signals.indicators import ema  # noqa: E402

CONFIG = Path("/freqtrade/user_data/config.paper.json")
BAKU = "Asia/Baku"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
FEEDS = ["https://www.coindesk.com/arc/outboundfeeds/rss/", "https://cointelegraph.com/rss"]
MAX_HEADLINES = 15
USER_AGENT = "Mozilla/5.0 (compatible; ai-trader-brief/1.0)"
# Mətndə həmişə icazəli kiçik rəqəmlər: dövrlər (24 saat, 7/30 gün), EMA 50/200, 7 cüt, 4h
BASE_NUMBERS = {1.0, 4.0, 7.0, 24.0, 30.0, 50.0, 200.0}

SYSTEM_PROMPT = """Sən kriptovalyuta bazarı üzrə qısa gündəlik icmal yazan analitiksən.
Qaydalar:
1. Yalnız Azərbaycan dilində yaz (latın əlifbası). Sadə, aydın cümlələr.
2. Yalnız istifadəçinin verdiyi faktlardan və xəbər başlıqlarından istifadə et. Özündən fakt,
   proqnoz, hədəf qiymət və ya xəbər əlavə etmə.
3. Hər rəqəmi faktlarda yazıldığı kimi, dəyişmədən köçür. Yeni rəqəm yazma, yuvarlaqlaşdırma.
4. Alış/satış tövsiyəsi vermə, "almaq lazımdır" kimi ifadələr işlətmə.
5. Quruluş: (a) ümumi mənzərə, 2-3 cümlə; (b) diqqətəlayiq cütlər, 2-4 cümlə;
   (c) xəbər başlıqlarından 2-3 əsas məqam (başlıq yoxdursa bu hissəni yazma).
6. Uzunluq: 120-220 söz. Markdown, ulduz, başlıq işarələri işlətmə — sadə mətn."""


# --- faktlar -----------------------------------------------------------------------

def pair_facts(d1: pd.DataFrame, h4: pd.DataFrame) -> dict:
    """d1: son ~31 gündəlik şam, h4: son ~300 4h şam (ən sonuncu = cari)."""
    close4 = h4["close"].astype(float).reset_index(drop=True)
    close1 = d1["close"].astype(float).reset_index(drop=True)
    price = float(close4.iloc[-1])
    e50, e200 = float(ema(close4, 50).iloc[-1]), float(ema(close4, 200).iloc[-1])
    if price > e50 > e200:
        trend = "yuxarı"
    elif price < e50 < e200:
        trend = "aşağı"
    else:
        trend = "qarışıq"

    def chg(base: float) -> float:
        return round((price / base - 1) * 100, 2)

    return {
        "price": round(price, 6 if price < 1 else 4 if price < 100 else 2),
        "chg_24h": chg(float(close4.iloc[-7])),
        "chg_7d": chg(float(close1.iloc[-8])),
        "chg_30d": chg(float(close1.iloc[-31])),
        "vol_30d": round(annual_volatility(close1.iloc[-31:]) * 100, 2),
        "trend": trend,
    }


def parse_rss(xml_text: str, now: pd.Timestamp, hours: int = 24) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        raw = item.findtext("pubDate")
        if not title or not raw:
            continue
        try:
            when = pd.Timestamp(parsedate_to_datetime(raw)).tz_convert("UTC")
        except (TypeError, ValueError):
            continue
        if pd.Timedelta(0) <= now - when <= pd.Timedelta(hours=hours):
            out.append(title)
    return out


# --- rəqəm yoxlaması -----------------------------------------------------------------

_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def _normalize(token: str) -> str:
    if "," in token and "." in token:
        return token.replace(",", "")
    if "," in token:
        return token.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", token) else token.replace(",", ".")
    return token


def _numbers(text: str) -> list[str]:
    return [_normalize(t) for t in _NUM.findall(text)]


def allowed_numbers(facts: dict, news: list[str], now: pd.Timestamp | None = None) -> set[float]:
    allowed = set(BASE_NUMBERS)
    for f in facts.values():
        allowed.update(abs(float(v)) for v in f.values() if isinstance(v, int | float))
    for title in news:
        allowed.update(float(n) for n in _numbers(title))
    if now is not None:
        local = now.tz_convert(BAKU)
        allowed.update({float(local.year), float(local.month), float(local.day)})
    return allowed


def unverified_numbers(text: str, allowed: set[float]) -> list[str]:
    """Mətndə faktlarda olmayan rəqəmlər. Faktın yuvarlaqlaşdırılmış forması da qəbul edilir."""
    bad = []
    for tok in _numbers(text):
        n = float(tok)
        dec = len(tok.split(".")[1]) if "." in tok else 0
        if not any(abs(n - a) < 1e-9 or abs(n - round(a, dec)) < 1e-9 for a in allowed):
            bad.append(tok)
    return bad


# --- prompt və LLM -------------------------------------------------------------------

def build_user_prompt(facts: dict, news: list[str], now: pd.Timestamp) -> str:
    local = now.tz_convert(BAKU)
    news_part = "\n".join(f"- {t}" for t in news) if news else "Son 24 saatda xəbər yoxdur."
    return (
        f"Tarix: {local:%Y-%m-%d} (Bakı vaxtı).\n\n"
        "Faktlar (price = USDT, chg_* = faiz dəyişmə, vol_30d = illik volatillik %, "
        "trend = 4 saatlıq EMA50/EMA200 vəziyyəti):\n"
        f"{json.dumps(facts, ensure_ascii=False, indent=1)}\n\n"
        f"Xəbər başlıqları (ingiliscə, son 24 saat):\n{news_part}\n\n"
        "Bu məlumatlar əsasında qaydalara uyğun icmal yaz."
    )


def groq_payload(key: str, model: str, system: str, user_or_messages) -> tuple[str, dict, dict]:
    msgs = user_or_messages if isinstance(user_or_messages, list) else [
        {"role": "user", "content": user_or_messages}]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json",
               "User-Agent": USER_AGENT}
    body = {"model": model, "temperature": 0.2, "max_tokens": 900,
            "messages": [{"role": "system", "content": system}, *msgs]}
    return GROQ_URL, headers, body


def groq_error(code: int, body: bytes, key: str) -> str:
    """Groq xətasının səbəbi (code + message). Açar mətndə görünsə gizlədilir."""
    msg = f"Groq HTTP {code}"
    try:
        err = json.loads(body).get("error", {})
        reason = " ".join(str(x) for x in (err.get("code"), err.get("message")) if x)
    except (ValueError, AttributeError):
        return msg
    if reason:
        msg += ": " + reason[:200]
    return msg.replace(key, "***") if key else msg


def groq_completer(key: str, model: str):
    def complete(system: str, messages: list) -> str:
        url, headers, body = groq_payload(key, model, system, messages)
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (sabit https ünvanı)
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raise RuntimeError(groq_error(e.code, e.read(), key)) from e
        return data["choices"][0]["message"]["content"].strip()

    return complete


def groq_models(key: str) -> list[str]:
    req = urllib.request.Request("https://api.groq.com/openai/v1/models",
                                 headers={"Authorization": f"Bearer {key}", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(groq_error(e.code, e.read(), key)) from e
    return sorted(m["id"] for m in data.get("data", []))


def write_brief(complete, facts: dict, news: list[str], now: pd.Timestamp) -> tuple[str | None, str | None]:
    """(mətn, None) uğurda; (None, səbəb) uğursuzluqda. Uydurma rəqəmdə 1 düzəliş cəhdi."""
    allowed = allowed_numbers(facts, news, now)
    messages = [{"role": "user", "content": build_user_prompt(facts, news, now)}]
    bad: list[str] = []
    for attempt in range(2):
        try:
            text = complete(SYSTEM_PROMPT, messages)
        except Exception as e:  # noqa: BLE001 — istənilən API/şəbəkə xətası açıq göstərilir
            return None, f"{type(e).__name__}: {e}"
        bad = unverified_numbers(text, allowed)
        if not bad:
            return text, None
        messages += [
            {"role": "assistant", "content": text},
            {"role": "user", "content": "Bu rəqəmlər faktlarda yoxdur: " + ", ".join(bad)
             + ". Onları çıxar və yalnız verilən faktlardakı rəqəmlərlə yenidən yaz."},
        ]
    return None, "faktlarda olmayan rəqəmlər: " + ", ".join(bad)


# --- mesaj ---------------------------------------------------------------------------

def _price(x: float) -> str:
    return f"{x:.2f}" if x >= 100 else f"{x:.4f}" if x >= 1 else f"{x:.6f}"


def facts_table(facts: dict) -> str:
    rows = []
    for pair, f in facts.items():
        rows.append(f"{pair}: {_price(f['price'])} | 24s {f['chg_24h']:+.2f}% | 7g {f['chg_7d']:+.2f}% "
                    f"| 30g {f['chg_30d']:+.2f}% | trend {f['trend']}")
    return "\n".join(rows)


def compose_message(facts: dict, now: pd.Timestamp, ai_text: str | None, error: str | None) -> str:
    local = now.tz_convert(BAKU)
    parts = [f"🧭 Bazar icmalı ({local:%Y-%m-%d} Bakı)", "", facts_table(facts), ""]
    if ai_text:
        parts.append(ai_text)
    else:
        parts.append(f"⚠️ AI icmalı bu gün alınmadı ({error}). Yuxarıdakı rəqəmlər kodla hesablanıb.")
    parts += ["", "ℹ️ Məlumat xarakterlidir, ticarət tövsiyəsi deyil. Bot-un qərarlarına təsir etmir."]
    return "\n".join(parts)


# --- şəbəkə (yalnız serverdə işləyir) ----------------------------------------------

def fetch_facts(config: dict) -> dict:
    import ccxt

    ex = ccxt.binance(config["exchange"].get("ccxt_config", {}))
    cols = ["date", "open", "high", "low", "close", "volume"]
    out = {}
    for pair in config["exchange"]["pair_whitelist"]:
        d1 = pd.DataFrame(ex.fetch_ohlcv(pair, "1d", limit=31), columns=cols)
        h4 = pd.DataFrame(ex.fetch_ohlcv(pair, "4h", limit=300), columns=cols)
        out[pair] = pair_facts(d1, h4)
    return out


def fetch_news(now: pd.Timestamp) -> list[str]:
    titles: list[str] = []
    for url in FEEDS:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                titles += parse_rss(resp.read().decode("utf-8", "replace"), now)
        except Exception as e:  # noqa: BLE001 — bir mənbənin xətası icmalı dayandırmır
            print(f"XƏBƏRDARLIQ: {url} oxunmadı: {e}", file=sys.stderr)
    return list(dict.fromkeys(titles))[:MAX_HEADLINES]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--send", action="store_true", help="Telegram-a göndər")
    parser.add_argument("--list-models", action="store_true", help="Groq-da açıq modelləri göstər")
    args = parser.parse_args()
    key = os.environ.get("GROQ_API_KEY", "")
    if args.list_models:
        print("\n".join(groq_models(key)) if key else "GROQ_API_KEY yoxdur")
        return 0

    config = json.loads(args.config.read_text())
    now = pd.Timestamp.now(tz="UTC")
    facts = fetch_facts(config)
    news = fetch_news(now)
    if key:
        model = os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        text, err = write_brief(groq_completer(key, model), facts, news, now)
    else:
        text, err = None, "GROQ_API_KEY təyin edilməyib"
    message = compose_message(facts, now, text, err)
    print(message)
    print(f"\n[xəbər başlıqları: {len(news)}]")
    if args.send:
        from paper_report import send_telegram

        send_telegram(message)
        print("Telegram: göndərildi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
