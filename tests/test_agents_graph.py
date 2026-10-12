"""Agent qrafı (LangGraph) — saxta LLM ilə. langgraph yoxdursa (Freqtrade konteyneri) skip."""

import json

import pandas as pd
import pytest

pytest.importorskip("langgraph")

from langchain_core.language_models.fake_chat_models import FakeListChatModel  # noqa: E402

from agents.graph import build_graph, run_agent  # noqa: E402
from agents.schemas import RiskReport  # noqa: E402

NOW = pd.Timestamp("2026-10-12 06:10", tz="UTC")
PAIRS = ["BTC/USDT", "ETH/USDT"]
FACTS = {
    "BTC/USDT": {"price": 84000.5, "chg_24h": 1.2, "chg_7d": -2.0, "chg_30d": 8.7, "vol_30d": 40.1,
                 "trend": "yuxarı", "rsi14": 61.3, "atr14": 1200.0, "atr_pct": 1.43},
    "ETH/USDT": {"price": 2565.7, "chg_24h": 2.6, "chg_7d": -5.3, "chg_30d": 1.6, "vol_30d": 52.0,
                 "trend": "aşağı", "rsi14": 44.0, "atr14": 60.0, "atr_pct": 2.34},
}
RISK_FACTS = {"avg_corr_30d": 0.81, "btc_dd_30d": 3.5}
NEWS = ["Bitcoin ETF inflows hit $500M"]


def j(obj):
    return json.dumps(obj, ensure_ascii=False)


TECH_OK = j({"views": [
    {"pair": "BTC/USDT", "bias": "yuxarı", "confidence": 0.7, "reasons": ["Trend yuxarı, RSI 61.3"]},
    {"pair": "ETH/USDT", "bias": "aşağı", "confidence": 0.6, "reasons": ["7 gündə -5.3%"]}]})
NEWS_OK = j({"views": [
    {"pair": "BTC/USDT", "sentiment": "müsbət", "events": ["ETF-lərə 500M axın"]},
    {"pair": "ETH/USDT", "sentiment": "neytral", "events": []}]})
RISK_OK = j({"regime": "normal", "max_new": 1, "reasons": ["Korrelyasiya 0.81, BTC düşüşü 3.5%"]})
SUP_OK = j({"summary": "BTC güclüdür.", "decisions": [
    {"pair": "BTC/USDT", "action": "AL", "confidence": 0.65, "rationale": "Trend və xəbər müsbət"},
    {"pair": "ETH/USDT", "action": "GÖZLƏ", "confidence": 0.5, "rationale": "Trend aşağı"}]})


def fake(*responses):
    return FakeListChatModel(responses=list(responses))


def run(tech, news, risk, sup, positions=None):
    g = build_graph({"texniki": tech, "xəbər": news, "risk": risk, "supervayzer": sup})
    return g.invoke({"pairs": PAIRS, "facts": FACTS, "risk_facts": RISK_FACTS, "news": NEWS,
                     "positions": positions or [], "now": NOW.isoformat(), "reports": {}})


def test_happy_path_all_agents_and_supervisor():
    out = run(fake(TECH_OK), fake(NEWS_OK), fake(RISK_OK), fake(SUP_OK))
    assert all(r["ok"] for r in out["reports"].values())
    assert out["decision"]["ok"] and out["decision"]["actions"] == {"BTC/USDT": "AL", "ETH/USDT": "GÖZLƏ"}
    assert out["decision"]["max_new"] == 1   # risk analitikinin limiti


def test_invalid_json_twice_marks_agent_failed_but_graph_continues():
    out = run(fake("bu JSON deyil", "yenə yox"), fake(NEWS_OK), fake(RISK_OK), fake(SUP_OK))
    assert out["reports"]["texniki"]["ok"] is False and "JSON" in out["reports"]["texniki"]["error"]
    assert out["decision"]["ok"]


def test_supervisor_is_told_which_agent_failed():
    sup = fake(SUP_OK)
    run(fake("x", "y"), fake(NEWS_OK), fake(RISK_OK), sup)
    # FakeListChatModel son çağırışın mesajlarını saxlamır — ona görə prompt qurucusunu yoxlayırıq
    from agents.prompts import supervisor_user_prompt
    p = supervisor_user_prompt(PAIRS, FACTS, {"texniki": {"ok": False, "error": "JSON xətası"},
                                              "xəbər": {"ok": True, "data": {}},
                                              "risk": {"ok": True, "data": {}}}, [], NOW)
    assert "texniki" in p and "UĞURSUZ" in p


def test_risk_agent_failure_means_no_new_positions():
    out = run(fake(TECH_OK), fake(NEWS_OK), fake("x", "y"), fake(SUP_OK))
    assert out["decision"]["max_new"] == 0   # ehtiyatlı: risk bilinmirsə yeni mövqe yox


def test_supervisor_failure_is_all_wait():
    out = run(fake(TECH_OK), fake(NEWS_OK), fake(RISK_OK), fake("x", "y"))
    d = out["decision"]
    assert d["ok"] is False and set(d["actions"].values()) == {"GÖZLƏ"} and d["error"]


def test_missing_pair_in_supervisor_output_is_rejected_then_retried():
    partial = j({"summary": "s", "decisions": [
        {"pair": "BTC/USDT", "action": "AL", "confidence": 0.6, "rationale": "r"}]})
    out = run(fake(TECH_OK), fake(NEWS_OK), fake(RISK_OK), fake(partial, SUP_OK))
    assert out["decision"]["ok"] and out["decision"]["actions"]["ETH/USDT"] == "GÖZLƏ"


def test_invented_number_triggers_retry_then_accepts_corrected():
    bad = j({"regime": "normal", "max_new": 1, "reasons": ["BTC 95000-ə çatacaq"]})
    out = run(fake(TECH_OK), fake(NEWS_OK), fake(bad, RISK_OK), fake(SUP_OK))
    assert out["reports"]["risk"]["ok"]


def test_run_agent_strips_code_fences():
    llm = fake("```json\n" + RISK_OK + "\n```")
    obj, err = run_agent(llm, "sys", "user", RiskReport, allowed={0.81, 3.5})
    assert err is None and obj.max_new == 1
