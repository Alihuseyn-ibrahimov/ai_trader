import pandas as pd
import pytest

from risk_audit import audit_trades

FEE = 0.0015


def trade(open_, close, stake, open_rate, stop, profit, reason="exit_signal", tag=None):
    return {
        "pair": "BTC/USDT",
        "open_date": pd.Timestamp(open_, tz="UTC"),
        "close_date": pd.Timestamp(close, tz="UTC"),
        "stake_amount": stake,
        "amount": stake / open_rate,
        "open_rate": open_rate,
        "initial_stop_loss_abs": stop,
        "fee_open": FEE,
        "fee_close": FEE,
        "profit_abs": profit,
        "exit_reason": reason,
        "enter_tag": tag,
    }


def run(rows, **kw):
    params = dict(starting_balance=1000.0, risk_pct=0.01, floor_ratio=0.7, max_open_trades=2)
    params.update(kw)
    return audit_trades(pd.DataFrame(rows), **params)


def test_planned_risk_within_limit_passes():
    # stake 180, stop 5% aşağı → itki ≈ 9 + komissiya ≈ 9.5 < 10
    r = run([trade("2023-01-01", "2023-01-02", 180, 100, 95, 5)])
    assert r["checks"]["risk_per_trade"] is True
    assert r["max_planned_risk"] == pytest.approx((1.8 * 5 + 1.8 * 100 * FEE + 1.8 * 95 * FEE) / 1000)


def test_oversized_trade_fails():
    r = run([trade("2023-01-01", "2023-01-02", 1000, 100, 95, 5)])  # tam balans → 5%+ risk
    assert r["checks"]["risk_per_trade"] is False


def test_equity_at_open_uses_only_previously_closed_trades():
    rows = [
        trade("2023-01-01", "2023-01-02", 180, 100, 95, -100),  # bağlandı → kapital 900
        trade("2023-01-03", "2023-01-04", 170, 100, 95, 0),     # 900-ün ~1%-i
    ]
    r = run(rows)
    assert r["equity_at_open"] == pytest.approx([1000, 900])


def test_concurrent_open_trades():
    rows = [
        trade("2023-01-01", "2023-01-05", 100, 100, 95, 0),
        trade("2023-01-02", "2023-01-06", 100, 100, 95, 0),
        trade("2023-01-03", "2023-01-04", 100, 100, 95, 0),
    ]
    r = run(rows)
    assert r["max_concurrent"] == 3
    assert r["checks"]["max_open_trades"] is False


def test_back_to_back_trades_are_not_concurrent():
    rows = [
        trade("2023-01-01", "2023-01-02", 100, 100, 95, 0),
        trade("2023-01-02", "2023-01-03", 100, 100, 95, 0),
    ]
    assert run(rows)["max_concurrent"] == 1


def test_floor_and_min_equity():
    rows = [trade("2023-01-01", "2023-01-02", 180, 100, 95, -350)]
    r = run(rows)
    assert r["min_equity"] == pytest.approx(650)
    assert r["checks"]["floor"] is False


def test_worst_actual_loss_reveals_gap_through_stop():
    # stop 95, amma qiymət 80-ə boşluqla düşüb: faktiki itki planlaşdırılandan böyük
    r = run([trade("2023-01-01", "2023-01-02", 180, 100, 95, -36)])
    assert r["worst_actual_loss"] == pytest.approx(0.036)


def test_exit_reasons_counted():
    rows = [
        trade("2023-01-01", "2023-01-02", 100, 100, 95, 0, "stop_loss"),
        trade("2023-01-03", "2023-01-04", 100, 100, 95, 0, "floor_kill_switch"),
    ]
    assert run(rows)["exit_reasons"] == {"stop_loss": 1, "floor_kill_switch": 1}


def test_empty_trades():
    r = run([])
    assert r["n_trades"] == 0


def test_planned_stop_taken_from_enter_tag_when_present():
    # Freqtrade initial_stop_loss_abs sabit backstop-dur (məs. -15% → 85);
    # əsl planlaşdırılan stop tag-dadır: 100 - 5 = 95
    r = run([trade("2023-01-01", "2023-01-02", 180, 100, 85, 0, tag="trend|sd=5")])
    assert r["max_planned_risk"] == pytest.approx((1.8 * 5 + 1.8 * 100 * FEE + 1.8 * 95 * FEE) / 1000)
