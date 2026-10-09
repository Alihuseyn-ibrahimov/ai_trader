import pandas as pd
import pytest

from paper_report import (
    build_report,
    current_equity,
    load_history,
    record_snapshot,
    report_state,
    telegram_payload,
)

START = 10_000.0
NOW = pd.Timestamp("2026-11-10 05:00", tz="UTC")


def trades(rows):
    base = {"fee_open": 0.001, "fee_close": 0.001, "enter_tag": None}
    df = pd.DataFrame([{**base, **r} for r in rows])
    for col in ("open_date", "close_date"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


CLOSED_WIN = dict(pair="ETH/USDT", is_open=False, open_date="2026-10-20", close_date="2026-11-01",
                  amount=1.0, open_rate=2000.0, stake_amount=2000.0, profit_abs=300.0)
CLOSED_LOSS = dict(pair="BTC/USDT", is_open=False, open_date="2026-10-21", close_date="2026-10-25",
                   amount=0.01, open_rate=60000.0, stake_amount=600.0, profit_abs=-50.0)
OPEN_SOL = dict(pair="SOL/USDT", is_open=True, open_date="2026-11-05", close_date=None,
                amount=10.0, open_rate=100.0, stake_amount=1000.0, profit_abs=0.0,
                enter_tag="trend|sd=8.0")


def test_equity_without_trades_is_start_balance():
    assert current_equity(trades([CLOSED_WIN]).iloc[0:0], {}, START) == START


def test_equity_counts_realized_and_open_mark_to_market():
    df = trades([CLOSED_WIN, CLOSED_LOSS, OPEN_SOL])
    eq = current_equity(df, {"SOL/USDT": 110.0}, START)
    # 10000 + 300 − 50 + (10·110·0.999 − 1000·1.001) = 10250 + 97.9
    assert eq == pytest.approx(10_347.9)


def test_open_position_without_price_fails_loudly():
    with pytest.raises(KeyError):
        current_equity(trades([OPEN_SOL]), {}, START)


def test_snapshot_one_row_per_day_and_history(tmp_path):
    path = tmp_path / "equity.csv"
    record_snapshot(path, pd.Timestamp("2026-11-08", tz="UTC"), 10_100.0)
    record_snapshot(path, pd.Timestamp("2026-11-09", tz="UTC"), 10_400.0)
    record_snapshot(path, pd.Timestamp("2026-11-09", tz="UTC"), 10_300.0)  # eyni gün → yenilənir
    h = load_history(path)
    assert list(h.values) == [10_100.0, 10_300.0]


def test_load_history_missing_file_is_empty(tmp_path):
    assert load_history(tmp_path / "yoxdur.csv").empty


def test_state_drawdown_from_history_peak():
    history = pd.Series([10_000.0, 11_000.0, 10_500.0])
    s = report_state(trades([CLOSED_WIN]), {}, START, 0.7, history, 9_900.0)
    assert s["drawdown"] == pytest.approx(1 - 9_900 / 11_000)
    assert s["floor"] == 7_000.0
    assert s["day_pnl"] == pytest.approx(9_900 - 10_500)
    assert s["n_closed"] == 1


def test_state_alerts_follow_plan_section_5():
    history = pd.Series([10_000.0, 12_500.0])
    s = report_state(trades([CLOSED_WIN]), {}, START, 0.7, history, 9_990.0)  # DD 20.08%
    assert "drawdown_stop" in s["alerts"]
    s = report_state(trades([CLOSED_WIN]), {}, START, 0.7, pd.Series(dtype=float), 6_990.0)
    assert "floor" in s["alerts"]
    many = trades([CLOSED_WIN] * 30)
    s = report_state(many, {}, START, 0.7, pd.Series(dtype=float), 10_000.0)
    assert s["alerts"] == ["final_eval"]


def test_report_text_in_azerbaijani_with_key_numbers():
    df = trades([CLOSED_WIN, CLOSED_LOSS, OPEN_SOL])
    prices = {"SOL/USDT": 110.0}
    history = pd.Series([10_000.0, 10_300.0])
    eq = current_equity(df, prices, START)
    text = build_report(report_state(df, prices, START, 0.7, history, eq), NOW)
    assert "Kapital: 10 347.90 USDT" in text
    assert "Alt xətt: 7 000.00 USDT" in text
    assert "Bağlanmış əməliyyat: 2/30" in text
    assert "SOL/USDT" in text and "stop 92.0000" in text  # giriş 100 − sd 8
    assert "⛔" not in text


def test_report_text_shows_stop_alert():
    history = pd.Series([10_000.0, 12_500.0])
    s = report_state(trades([CLOSED_WIN]), {}, START, 0.7, history, 9_990.0)
    assert "⛔" in build_report(s, NOW)


def test_telegram_payload_never_contains_token():
    url, body = telegram_payload("SECRET123", "42", "salam")
    assert url == "https://api.telegram.org/botSECRET123/sendMessage"
    assert body == {"chat_id": "42", "text": "salam"}
