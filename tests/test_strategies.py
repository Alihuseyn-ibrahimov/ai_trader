"""Strategiya faylları siqnal modulunu düzgün bağlayırmı (konteynerdə)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("freqtrade")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "user_data" / "strategies"))

from meanrev_rsi_bb import MeanRevRsiBb  # noqa: E402
from signals.meanrev import meanrev_signals  # noqa: E402
from signals.trend import trend_signals  # noqa: E402
from trend_ema_atr import TrendEmaAtr  # noqa: E402

CFG = {"stake_currency": "USDT", "ai_risk": {}}


def candles(n=600, seed=3):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    return pd.DataFrame({
        "date": pd.date_range("2023-01-01", periods=n, freq="1h", tz="UTC"),
        "open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
        "volume": 1.0,
    })


def run(strategy):
    df = candles()
    meta = {"pair": "BTC/USDT"}
    df = strategy.populate_indicators(df, meta)
    df = strategy.populate_entry_trend(df, meta)
    return strategy.populate_exit_trend(df, meta)


@pytest.mark.parametrize(
    "cls,signal_fn,params,timeframe,trailing",
    [
        (TrendEmaAtr, trend_signals,
         dict(ema_fast=50, ema_slow=200, atr_period=14, atr_mult=3.0), "4h", True),
        (MeanRevRsiBb, meanrev_signals,
         dict(bb_period=20, rsi_entry=30.0, atr_mult=2.0, trend_ema=200), "1h", False),
    ],
)
def test_strategy_matches_signal_module(cls, signal_fn, params, timeframe, trailing):
    s = cls(CFG)
    assert s.timeframe == timeframe
    assert s.use_custom_stoploss is True
    assert s.atr_trailing is trailing
    assert s.startup_candle_count >= 400
    assert s.params == params  # planda sabitlənmiş dəyərlər — dəyişmək plan dəyişikliyidir

    out = run(s)
    expected = signal_fn(candles(), **params)
    assert out["enter_long"].fillna(0).astype(int).tolist() == expected["enter_long"].tolist()
    assert out["exit_long"].fillna(0).astype(int).tolist() == expected["exit_long"].tolist()
    entries = expected["enter_long"] == 1
    assert out.loc[entries, "enter_tag"].tolist() == expected.loc[entries, "enter_tag"].tolist()


@pytest.mark.parametrize("cls", [TrendEmaAtr, MeanRevRsiBb])
def test_roi_disabled_and_backstop_wider_than_typical_atr_stop(cls):
    assert min(cls.minimal_roi.values()) >= 10  # ROI söndürülüb: çıxış yalnız siqnal/stop
    assert -0.20 <= cls.stoploss <= -0.10
