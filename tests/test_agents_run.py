"""Gündəlik kölgə dövrü (agents/run.py) — saxta qraf ilə, şəbəkəsiz."""

from pathlib import Path

import pandas as pd
import pytest

if not (Path(__file__).resolve().parent.parent / "agents").exists():
    # Freqtrade konteynerində agents/ mount olunmur — bu testlər host/agent imicindədir
    pytest.skip("agents/ yoxdur (Freqtrade konteyneri)", allow_module_level=True)

from agents.run import (already_ran, append_rows, compose_message, decision_rows,  # noqa: E402
                        h4_frame, run_cycle)
from agents.shadow import ShadowBook  # noqa: E402

NOW = pd.Timestamp("2026-10-12 06:10", tz="UTC")
PAIRS = ["A/USDT", "B/USDT"]
FACTS = {"A/USDT": {"price": 10.0, "atr14": 0.5}, "B/USDT": {"price": 20.0, "atr14": 1.0}}


class FakeGraph:
    def __init__(self, actions, max_new=1, ok=True):
        self.out = {"reports": {"texniki": {"ok": True, "data": {}, "error": None},
                                "xəbər": {"ok": False, "data": None, "error": "JSON xətası"},
                                "risk": {"ok": True, "data": {"max_new": max_new}, "error": None}},
                    "decision": {"ok": ok, "error": None if ok else "x", "max_new": max_new,
                                 "summary": "Qısa xülasə." if ok else None, "actions": actions,
                                 "details": [{"pair": p, "action": a, "confidence": 0.6,
                                              "rationale": f"{p} səbəb"} for p, a in actions.items()]}}
        self.state = None

    def invoke(self, state):
        self.state = state
        return self.out


def candles(rows):
    return {p: pd.DataFrame(r, columns=["date", "open", "high", "low", "close"]) for p, r in rows.items()}


def test_cycle_opens_positions_within_risk_limit_and_passes_positions_to_agents():
    book = ShadowBook()
    g = FakeGraph({"A/USDT": "AL", "B/USDT": "AL"}, max_new=1)
    r = run_cycle(book, g, PAIRS, FACTS, {}, {"avg_corr_30d": 0.8}, ["x"], NOW)
    assert r["events"] == {"A/USDT": "açıldı", "B/USDT": "risk limiti"}
    assert list(book.positions) == ["A/USDT"] and book.positions["A/USDT"].stop == pytest.approx(8.5)
    assert g.state["positions"] == [] and g.state["now"] == NOW.isoformat() and g.state["reports"] == {}


def test_stops_are_checked_before_agents_see_positions():
    book = ShadowBook()
    book.apply({"A/USDT": "AL"}, {"A/USDT": 10.0}, {"A/USDT": 0.5}, NOW - pd.Timedelta(days=1), 2)
    h4 = candles({"A/USDT": [[NOW - pd.Timedelta(hours=10), 9.0, 9.1, 8.0, 8.2]]})
    g = FakeGraph({"A/USDT": "GÖZLƏ", "B/USDT": "GÖZLƏ"})
    r = run_cycle(book, g, PAIRS, FACTS, h4, {}, [], NOW)
    assert r["stops"] == ["A/USDT"] and g.state["positions"] == [] and book.trades[0]["exit"] == 8.5


def test_failed_supervisor_opens_nothing():
    book = ShadowBook()
    r = run_cycle(book, FakeGraph({"A/USDT": "GÖZLƏ", "B/USDT": "GÖZLƏ"}, ok=False),
                  PAIRS, FACTS, {}, {}, [], NOW)
    assert book.positions == {} and r["events"] == {}


def test_decision_rows_log_prompt_version_agent_status_and_outcome():
    book = ShadowBook()
    r = run_cycle(book, FakeGraph({"A/USDT": "AL", "B/USDT": "GÖZLƏ"}), PAIRS, FACTS, {}, {}, [], NOW)
    rows = decision_rows(r, FACTS, NOW, "v1")
    a = next(x for x in rows if x["pair"] == "A/USDT")
    assert a["action"] == "AL" and a["outcome"] == "açıldı" and a["price"] == 10.0
    assert a["prompt_version"] == "v1" and a["time"] == NOW.isoformat()
    assert a["agents_failed"] == "xəbər" and a["decision_ok"] is True
    b = next(x for x in rows if x["pair"] == "B/USDT")
    assert b["outcome"] == ""


def test_append_rows_and_already_ran_by_baku_date(tmp_path):
    path = tmp_path / "decisions.csv"
    assert not already_ran(path, NOW)
    append_rows(path, [{"time": NOW.isoformat(), "pair": "A/USDT"}])
    append_rows(path, [{"time": NOW.isoformat(), "pair": "B/USDT"}])
    assert len(pd.read_csv(path)) == 2                                    # başlıq bir dəfə
    assert already_ran(path, NOW + pd.Timedelta(hours=10))               # 16:10 UTC = eyni Bakı günü
    assert not already_ran(path, NOW + pd.Timedelta(hours=18))            # 00:10 UTC → Bakı 04:10 ertəsi


def test_message_is_marked_shadow_and_shows_failures():
    book = ShadowBook()
    r = run_cycle(book, FakeGraph({"A/USDT": "AL", "B/USDT": "GÖZLƏ"}), PAIRS, FACTS, {}, {}, [], NOW)
    msg = compose_message(r, book, FACTS, NOW)
    assert msg.startswith("🕶 KÖLGƏ — icra olunmur")
    assert "A/USDT" in msg and "AL" in msg and "açıldı" in msg
    assert "xəbər" in msg and "UĞURSUZ" in msg
    assert "10000" in msg.replace(" ", "") or "10 000" in msg


def test_message_when_supervisor_failed_says_all_wait():
    book = ShadowBook()
    r = run_cycle(book, FakeGraph({"A/USDT": "GÖZLƏ", "B/USDT": "GÖZLƏ"}, ok=False),
                  PAIRS, FACTS, {}, {}, [], NOW)
    msg = compose_message(r, book, FACTS, NOW)
    assert "supervayzer" in msg.lower() and "GÖZLƏ" in msg


def test_h4_frame_converts_ccxt_ms_to_utc_dates():
    df = h4_frame([[1760248800000, 1.0, 2.0, 0.5, 1.5, 10.0]])
    assert df["date"].iloc[0] == pd.Timestamp("2025-10-12 06:00", tz="UTC")


def test_tracing_disabled_without_langsmith_key():
    from agents.run import configure_tracing
    env = {"LANGSMITH_TRACING": "true"}
    assert configure_tracing(env) is not None and env["LANGSMITH_TRACING"] == "false"
    env = {"LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "x"}
    assert configure_tracing(env) is None and env["LANGSMITH_TRACING"] == "true"
