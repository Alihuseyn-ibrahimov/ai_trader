"""Agentlər: kodla hesablanan faktlar və kölgə portfel (LLM-siz, təmiz kod)."""

import numpy as np
import pandas as pd
import pytest

from agents.facts import risk_facts, technical_facts
from agents.shadow import FEE, RISK_PCT, ShadowBook

T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def flat(n, freq, end, close=100.0, rng=2.0):
    idx = pd.date_range(end=end, periods=n, freq=freq, tz="UTC")
    c = np.full(n, close)
    return pd.DataFrame({"date": idx, "open": c, "high": c + rng / 2, "low": c - rng / 2,
                         "close": c, "volume": 1.0})


# --- faktlar ----------------------------------------------------------------------

def test_technical_facts_atr_and_rsi_by_hand():
    f = technical_facts(flat(31, "1D", "2026-10-11"), flat(300, "4h", "2026-10-12 04:00"))
    assert f["atr14"] == pytest.approx(2.0)          # hər şamda high − low = 2
    assert f["atr_pct"] == pytest.approx(2.0)        # 2 / 100
    assert 0 <= f["rsi14"] <= 100
    assert {"price", "chg_24h", "chg_7d", "chg_30d", "vol_30d", "trend"} <= set(f)


def test_risk_facts_correlation_and_drawdown_by_hand():
    up = np.array([100.0, 102, 101, 104, 103, 106] * 6)[:31]
    d = {"BTC/USDT": pd.DataFrame({"close": up}), "ETH/USDT": pd.DataFrame({"close": up * 20})}
    r = risk_facts(d)
    assert r["avg_corr_30d"] == pytest.approx(1.0)   # eyni gəlirlər
    btc = pd.DataFrame({"close": [100.0] * 20 + [110.0] + [99.0] * 10})
    assert risk_facts({"BTC/USDT": btc, "ETH/USDT": btc})["btc_dd_30d"] == pytest.approx(10.0)


# --- kölgə portfel ----------------------------------------------------------------

def book():
    return ShadowBook(equity=10_000.0)


def test_open_position_sized_by_risk_module():
    b = book()
    ev = b.apply({"BTC/USDT": "AL"}, prices={"BTC/USDT": 100.0}, atrs={"BTC/USDT": 2.0},
                 now=T("2026-10-12 05:10"), max_new=2)
    p = b.positions["BTC/USDT"]
    assert p.stop == pytest.approx(94.0)             # 100 − 3×2
    loss_at_stop = p.amount * (100 - 94) + p.amount * 100 * FEE + p.amount * 94 * FEE
    assert loss_at_stop == pytest.approx(10_000 * RISK_PCT)  # 50 USDT
    assert ev == [("BTC/USDT", "açıldı")]


def test_max_two_positions_and_risk_regime_limit():
    b = book()
    prices = {"A/USDT": 10.0, "B/USDT": 10.0, "C/USDT": 10.0}
    atrs = {k: 0.5 for k in prices}
    ev = b.apply({k: "AL" for k in prices}, prices, atrs, T("2026-10-12"), max_new=2)
    assert len(b.positions) == 2 and ("C/USDT", "slot yoxdur") in ev
    b2 = book()
    ev2 = b2.apply({"A/USDT": "AL"}, prices, atrs, T("2026-10-12"), max_new=0)
    assert not b2.positions and ev2 == [("A/USDT", "risk limiti")]


def test_duplicate_buy_and_exit_without_position_are_ignored():
    b = book()
    b.apply({"A/USDT": "AL"}, {"A/USDT": 10.0}, {"A/USDT": 0.5}, T("2026-10-12"), 2)
    ev = b.apply({"A/USDT": "AL", "B/USDT": "ÇIX"}, {"A/USDT": 11.0, "B/USDT": 5.0},
                 {"A/USDT": 0.5, "B/USDT": 0.1}, T("2026-10-13"), 2)
    assert ("A/USDT", "artıq açıqdır") in ev and ("B/USDT", "mövqe yoxdur") in ev
    assert b.positions["A/USDT"].entry == 10.0


def test_exit_decision_realizes_pnl_with_fees():
    b = book()
    b.apply({"A/USDT": "AL"}, {"A/USDT": 10.0}, {"A/USDT": 0.5}, T("2026-10-12"), 2)
    amt = b.positions["A/USDT"].amount
    b.apply({"A/USDT": "ÇIX"}, {"A/USDT": 12.0}, {"A/USDT": 0.5}, T("2026-10-15"), 2)
    expected = amt * 12.0 * (1 - FEE) - amt * 10.0 * (1 + FEE)
    assert b.trades[-1]["pnl"] == pytest.approx(expected)
    assert b.trades[-1]["reason"] == "supervayzer"
    assert b.equity == pytest.approx(10_000 + expected) and not b.positions


def test_stop_hit_by_candle_low_and_gap_below_stop():
    b = book()
    b.apply({"A/USDT": "AL", "B/USDT": "AL"}, {"A/USDT": 10.0, "B/USDT": 10.0},
            {"A/USDT": 0.5, "B/USDT": 0.5}, T("2026-10-12 05:10"), 2)   # stop 8.5
    candles = {
        "A/USDT": pd.DataFrame({"date": [T("2026-10-12 08:00")], "open": [9.0], "low": [8.4]}),
        "B/USDT": pd.DataFrame({"date": [T("2026-10-12 08:00")], "open": [8.0], "low": [7.9]}),
    }
    closed = b.check_stops(candles)
    exits = {t["pair"]: t["exit"] for t in b.trades}
    assert set(closed) == {"A/USDT", "B/USDT"}
    assert exits["A/USDT"] == 8.5                    # şam içində stop
    assert exits["B/USDT"] == 8.0                    # açılış stopdan aşağı → açılışda (boşluq)


def test_candles_before_entry_do_not_trigger_stop():
    b = book()
    b.apply({"A/USDT": "AL"}, {"A/USDT": 10.0}, {"A/USDT": 0.5}, T("2026-10-12 05:10"), 2)
    old = {"A/USDT": pd.DataFrame({"date": [T("2026-10-12 04:00")], "open": [8.0], "low": [7.0]})}
    assert b.check_stops(old) == [] and "A/USDT" in b.positions


def test_state_roundtrip(tmp_path):
    b = book()
    b.apply({"A/USDT": "AL"}, {"A/USDT": 10.0}, {"A/USDT": 0.5}, T("2026-10-12"), 2)
    path = tmp_path / "state.json"
    b.save(path)
    c = ShadowBook.load(path)
    assert c.equity == b.equity and c.positions == b.positions and c.trades == b.trades


def test_load_missing_state_starts_fresh(tmp_path):
    c = ShadowBook.load(tmp_path / "yoxdur.json")
    assert c.equity == 10_000.0 and not c.positions
