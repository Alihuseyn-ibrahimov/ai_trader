import numpy as np
import pandas as pd
import pytest

from market_brief import (
    SYSTEM_PROMPT,
    allowed_numbers,
    build_user_prompt,
    compose_message,
    facts_table,
    groq_payload,
    pair_facts,
    parse_rss,
    unverified_numbers,
)

NOW = pd.Timestamp("2026-10-12 05:05", tz="UTC")


def candles(closes, freq, end):
    idx = pd.date_range(end=end, periods=len(closes), freq=freq, tz="UTC")
    c = np.asarray(closes, dtype=float)
    return pd.DataFrame({"date": idx, "open": c, "high": c, "low": c, "close": c, "volume": 1.0})


# --- faktlar (kod hesablayır, LLM yox) ------------------------------------------

def test_pair_facts_changes_by_hand():
    # 1d: 31 şam, son bağlanış 110; 7 gün əvvəl 100, 30 gün əvvəl 88
    d = [88.0] + [95.0] * 22 + [100.0] + [105.0] * 6 + [110.0]
    # 4h: son 7 şam — 24 saat əvvəl (6 şam geri) 104.5
    h = [100.0] * 293 + [104.5, 106, 107, 108, 109, 109.5, 110.0]
    f = pair_facts(candles(d, "1D", "2026-10-11"), candles(h, "4h", "2026-10-12 04:00"))
    assert f["price"] == 110.0
    assert f["chg_24h"] == pytest.approx(5.26, abs=0.005)    # 110/104.5 − 1
    assert f["chg_7d"] == pytest.approx(10.0, abs=0.005)     # 110/100 − 1
    assert f["chg_30d"] == pytest.approx(25.0, abs=0.005)    # 110/88 − 1
    assert f["trend"] in {"yuxarı", "aşağı", "qarışıq"}


def test_pair_facts_trend_states():
    up = pair_facts(candles([100.0] * 31, "1D", "2026-10-11"),
                    candles(np.linspace(50, 150, 300), "4h", "2026-10-12 04:00"))
    down = pair_facts(candles([100.0] * 31, "1D", "2026-10-11"),
                      candles(np.linspace(150, 50, 300), "4h", "2026-10-12 04:00"))
    assert up["trend"] == "yuxarı" and down["trend"] == "aşağı"


def test_facts_values_are_rounded_strings_safe():
    f = pair_facts(candles([100.0] * 31, "1D", "2026-10-11"),
                   candles([100.0] * 300, "4h", "2026-10-12 04:00"))
    for k in ("chg_24h", "chg_7d", "chg_30d", "vol_30d"):
        assert f[k] == round(f[k], 2)


# --- RSS -------------------------------------------------------------------------

RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Bitcoin climbs past $70K as ETF inflows hit $500M</title>
<pubDate>Sun, 12 Oct 2026 03:00:00 +0000</pubDate></item>
<item><title><![CDATA[Ethereum upgrade "Fusaka" goes live]]></title>
<pubDate>Sat, 11 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Old news from last week</title>
<pubDate>Mon, 06 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>No date item</title></item>
</channel></rss>"""


def test_parse_rss_keeps_last_24h_only():
    titles = parse_rss(RSS, NOW, hours=24)
    assert titles == ["Bitcoin climbs past $70K as ETF inflows hit $500M",
                      'Ethereum upgrade "Fusaka" goes live']


def test_parse_rss_broken_xml_returns_empty():
    assert parse_rss("<html>blocked</html", NOW) == []


# --- rəqəm yoxlaması (uydurma rəqəm → rədd) --------------------------------------

FACTS = {
    "BTC/USDT": {"price": 68123.45, "chg_24h": 2.31, "chg_7d": -4.1, "chg_30d": 12.0,
                 "vol_30d": 48.5, "trend": "yuxarı"},
}
NEWS = ["Bitcoin ETF inflows hit $500M"]


def test_numbers_from_facts_and_news_are_allowed():
    text = "BTC 68123.45 USDT, 24 saatda +2,31%, 7 gündə -4.1%, 30 gündə 12%. ETF-lərə 500M axın."
    assert unverified_numbers(text, allowed_numbers(FACTS, NEWS)) == []


def test_invented_number_is_caught():
    text = "BTC 24 saatda 2.31% artıb, analitiklər 80000 hədəfini gözləyir."
    assert unverified_numbers(text, allowed_numbers(FACTS, NEWS)) == ["80000"]


def test_slightly_wrong_number_is_caught():
    assert unverified_numbers("7 gündə -4.2%", allowed_numbers(FACTS, NEWS)) == ["4.2"]


# --- prompt -----------------------------------------------------------------------

def test_system_prompt_rules():
    for rule in ("azərbaycan", "yalnız", "tövsiyə", "rəqəm"):
        assert rule in SYSTEM_PROMPT.lower()
    assert "{" not in SYSTEM_PROMPT  # sabitdir, dəyişən daxil edilmir


def test_user_prompt_contains_facts_and_news():
    p = build_user_prompt(FACTS, NEWS, NOW)
    assert "68123.45" in p and "ETF inflows" in p and "2026-10-12" in p


def test_user_prompt_says_when_no_news():
    assert "xəbər yoxdur" in build_user_prompt(FACTS, [], NOW)


def test_groq_payload_has_no_key_in_body():
    url, headers, body = groq_payload("SECRET", "model-x", "sys", "usr")
    assert url == "https://api.groq.com/openai/v1/chat/completions"
    assert headers["Authorization"] == "Bearer SECRET"
    assert "SECRET" not in str(body)
    assert body["messages"][0] == {"role": "system", "content": "sys"}
    assert body["temperature"] <= 0.3


# --- yekun mesaj: uğursuzluq açıq görünür ----------------------------------------

def test_facts_table_is_deterministic():
    t = facts_table(FACTS)
    assert "BTC/USDT" in t and "68123.45" in t and "+2.31%" in t and "yuxarı" in t


def test_message_with_ai_text():
    m = compose_message(FACTS, NOW, ai_text="Bazar sakitdir.", error=None)
    assert "Bazar sakitdir." in m
    assert "⚠️" not in m
    assert "məlumat xarakterlidir" in m.lower()


def test_message_when_ai_failed_is_explicit():
    m = compose_message(FACTS, NOW, ai_text=None, error="Groq HTTP 429")
    assert "⚠️ AI icmalı bu gün alınmadı" in m and "Groq HTTP 429" in m
    assert "68123.45" in m  # faktlar yenə göndərilir


# --- LLM qatı: uydurma rəqəmdə 1 düzəliş cəhdi, sonra imtina ----------------------

def fake(replies):
    calls = []

    def complete(system, messages):
        calls.append(messages)
        r = replies[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    return complete, calls


def test_write_brief_accepts_clean_text_first_time():
    from market_brief import write_brief

    complete, calls = fake(["BTC 24 saatda 2.31% artıb."])
    assert write_brief(complete, FACTS, NEWS, NOW) == ("BTC 24 saatda 2.31% artıb.", None)
    assert len(calls) == 1


def test_write_brief_retries_once_with_correction():
    from market_brief import write_brief

    complete, calls = fake(["BTC 90000-ə çatacaq.", "BTC 24 saatda 2.31% artıb."])
    text, err = write_brief(complete, FACTS, NEWS, NOW)
    assert err is None and text == "BTC 24 saatda 2.31% artıb."
    assert "90000" in calls[1][-1]["content"]  # düzəliş tələbi səhv rəqəmi adlandırır


def test_write_brief_gives_up_after_second_invented_number():
    from market_brief import write_brief

    complete, _ = fake(["BTC 90000.", "BTC 95000."])
    text, err = write_brief(complete, FACTS, NEWS, NOW)
    assert text is None and "95000" in err


def test_write_brief_reports_api_error():
    from market_brief import write_brief

    complete, _ = fake([RuntimeError("Groq HTTP 429")])
    text, err = write_brief(complete, FACTS, NEWS, NOW)
    assert text is None and "Groq HTTP 429" in err


def test_groq_error_message_includes_reason_but_never_key():
    # Regressiya (serverdə ilk işləmə): yalnız "Groq HTTP 404" görünürdü, səbəb yox idi
    from market_brief import groq_error

    body = b'{"error":{"message":"The model `llama-x` does not exist","type":"invalid_request_error","code":"model_not_found"}}'
    msg = groq_error(404, body, key="gsk_SECRET")
    assert msg.startswith("Groq HTTP 404") and "model_not_found" in msg and "does not exist" in msg
    assert "gsk_SECRET" not in groq_error(401, b'{"error":{"message":"Invalid API Key gsk_SECRET"}}', key="gsk_SECRET")
    assert groq_error(502, b"<html>bad gateway</html>", key="k") == "Groq HTTP 502"


def test_default_model_exists_on_groq_and_reasoning_is_low():
    # 2026-10-12 serverdə: llama-3.3-70b-versatile → model_not_found; hesabda openai/gpt-oss-120b var
    from market_brief import DEFAULT_MODEL

    assert DEFAULT_MODEL == "openai/gpt-oss-120b"
    _, _, body = groq_payload("k", "openai/gpt-oss-120b", "s", "u")
    assert body["reasoning_effort"] == "low" and body["max_tokens"] >= 2000
    _, _, other = groq_payload("k", "qwen/qwen3.8-27b", "s", "u")
    assert "reasoning_effort" not in other  # başqa modellərə tanınmayan parametr göndərilmir


def test_empty_reply_is_failure_not_success():
    from market_brief import write_brief

    complete, _ = fake(["   "])
    text, err = write_brief(complete, FACTS, NEWS, NOW)
    assert text is None and "boş" in err
