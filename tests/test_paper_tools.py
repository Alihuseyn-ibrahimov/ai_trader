import pandas as pd
import pytest

from paper_eval import evaluate_paper
from parity import match_trades
from risk_audit import prepare_db_trades
from uptime import candle_coverage, merge_covered, parse_heartbeats

T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def opens(rows):
    return pd.DataFrame([{"pair": p, "open_date": T(d)} for p, d in rows])


# --- parity (meyar 6) -------------------------------------------------------

def test_parity_identical_trades_full_match():
    df = opens([("BTC/USDT", "2026-11-01 04:00"), ("ETH/USDT", "2026-11-03 08:00")])
    r = match_trades(df, df.copy())
    assert r["matched"] == 2 and r["ratio"] == 1.0


def test_parity_one_candle_tolerance_but_not_two():
    paper = opens([("BTC/USDT", "2026-11-01 08:00"), ("ETH/USDT", "2026-11-03 16:00")])
    bt = opens([("BTC/USDT", "2026-11-01 04:00"), ("ETH/USDT", "2026-11-03 08:00")])
    r = match_trades(paper, bt)
    assert r["matched"] == 1  # BTC ±1 şam; ETH 2 şam fərq → uyğun deyil


def test_parity_pair_must_match_and_each_trade_used_once():
    paper = opens([("BTC/USDT", "2026-11-01 04:00"), ("BTC/USDT", "2026-11-01 08:00")])
    bt = opens([("BTC/USDT", "2026-11-01 04:00"), ("SOL/USDT", "2026-11-01 08:00")])
    r = match_trades(paper, bt)
    assert r["matched"] == 1
    # ratio = uyğun / birləşmə = 1 / (2 + 2 − 1)
    assert r["ratio"] == pytest.approx(1 / 3)
    assert r["only_paper"] == 1 and r["only_backtest"] == 1


def test_parity_empty_is_undefined():
    empty = opens([])
    assert match_trades(empty, empty)["ratio"] is None


# --- uptime (meyar 7) -------------------------------------------------------

LOG = """\
2026-11-01 00:00:41,100 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.9', state='RUNNING'
2026-11-01 00:05:00,000 - freqtrade.freqtradebot - INFO - something else
2026-11-01 04:12:03,500 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.9', state='RUNNING'
2026-11-01 08:30:00,000 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.9', state='RUNNING'
2026-11-01 12:01:00,000 - freqtrade.worker - INFO - Bot heartbeat. PID=1, version='2026.9', state='STOPPED'
"""


def test_parse_heartbeats_only_running():
    hb = parse_heartbeats(LOG.splitlines())
    assert hb == [T("2026-11-01 00:00:41"), T("2026-11-01 04:12:03"), T("2026-11-01 08:30:00")]


def test_candle_counts_only_if_heartbeat_within_15_minutes_of_open():
    hb = parse_heartbeats(LOG.splitlines())
    covered, total = candle_coverage(hb, T("2026-11-01"), T("2026-11-01 16:00"))
    # şamlar: 00, 04, 08, 12 → 00 və 04 vaxtında; 08 (30 dəq gec) və 12 (STOPPED) yox
    assert total == 4
    assert covered == {T("2026-11-01 00:00"), T("2026-11-01 04:00")}


def test_merge_covered_persists_across_log_rotation(tmp_path):
    path = tmp_path / "uptime.csv"
    assert merge_covered(path, {T("2026-11-01 00:00")}) == {T("2026-11-01 00:00")}
    both = merge_covered(path, {T("2026-11-01 04:00")})
    assert both == {T("2026-11-01 00:00"), T("2026-11-01 04:00")}


# --- risk_audit DB rejimi ---------------------------------------------------

def test_prepare_db_trades_open_positions_count_as_open_until_now():
    df = pd.DataFrame({
        "open_date": [T("2026-11-01"), T("2026-11-02")],
        "close_date": [T("2026-11-03"), pd.NaT],
        "is_open": [False, True],
        "profit_abs": [10.0, None],
    })
    now = T("2026-11-05")
    out = prepare_db_trades(df, now)
    assert out["close_date"].tolist() == [T("2026-11-03"), now]
    assert out["profit_abs"].tolist() == [10.0, 0.0]  # açıq mövqenin reallaşmamış nəticəsi sayılmır


# --- paper_eval (§4 meyarları 1–4) ------------------------------------------

def test_evaluate_paper_all_pass():
    r = evaluate_paper({"n_trades": 31, "max_drawdown": 0.12, "profit_factor": 1.6, "net_return": 0.05})
    assert all(r["criteria"].values())


@pytest.mark.parametrize("metrics,failed", [
    ({"n_trades": 29, "max_drawdown": 0.1, "profit_factor": 2, "net_return": 0.1}, "1_trades"),
    ({"n_trades": 30, "max_drawdown": 0.2, "profit_factor": 2, "net_return": 0.1}, "2_drawdown"),
    ({"n_trades": 30, "max_drawdown": 0.1, "profit_factor": 1.2, "net_return": 0.1}, "3_profit_factor"),
    ({"n_trades": 30, "max_drawdown": 0.1, "profit_factor": 2, "net_return": 0.0}, "4_positive"),
])
def test_evaluate_paper_boundaries(metrics, failed):
    r = evaluate_paper(metrics)
    assert [k for k, ok in r["criteria"].items() if not ok] == [failed]


def test_prepare_db_trades_ms_resolution_dates_from_freqtrade_db():
    # Regressiya (e2e, real Freqtrade sqlite): DB tarixləri datetime64[ms, UTC];
    # mikrosaniyəli `now` yazılanda TypeError verirdi
    df = pd.DataFrame({
        "open_date": pd.Series([T("2026-11-01")]).astype("datetime64[ms, UTC]"),
        "close_date": pd.Series([pd.NaT], dtype="datetime64[ms, UTC]"),
        "is_open": [True],
        "profit_abs": [None],
    })
    out = prepare_db_trades(df, pd.Timestamp("2026-11-05 10:11:12.345678", tz="UTC"))
    assert out["close_date"].iloc[0] == T("2026-11-05 10:11")
