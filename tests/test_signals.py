"""Siqnal məntiqi — süni qiymət seriyaları ilə (yalnız qaydaların düzgünlüyü üçün)."""

import numpy as np
import pandas as pd
import pytest

from signals.indicators import atr, bollinger, ema, rsi
from signals.meanrev import meanrev_signals
from signals.tags import parse_stop_dist
from signals.trend import trend_signals

TREND = dict(ema_fast=3, ema_slow=8, atr_period=3, atr_mult=3.0)
MR = dict(bb_period=20, rsi_entry=40.0, atr_mult=2.0, trend_ema=100)


def frame(close):
    close = pd.Series(close, dtype=float)
    return pd.DataFrame({"open": close, "high": close + 0.5, "low": close - 0.5, "close": close})


class TestTrend:
    def test_no_entry_in_downtrend(self):
        out = trend_signals(frame(np.linspace(200, 100, 80)), **TREND)
        assert out["enter_long"].sum() == 0

    def test_entry_on_recovery_above_fast_ema_in_uptrend(self):
        close = list(np.linspace(100, 160, 60)) + [150, 145, 150, 158, 165, 170]
        df = trend_signals(frame(close), **TREND)
        fast, slow = ema(df["close"], 3), ema(df["close"], 8)
        entries = df.index[df["enter_long"] == 1].tolist()
        assert entries, "bərpa şamında giriş gözlənilirdi"
        for i in entries:
            assert fast[i] > slow[i]
            assert df["close"][i] > fast[i] and df["close"][i - 1] <= fast[i - 1]

    def test_exit_when_fast_crosses_below_slow(self):
        close = list(np.linspace(100, 160, 40)) + list(np.linspace(160, 100, 40))
        df = trend_signals(frame(close), **TREND)
        fast, slow = ema(df["close"], 3), ema(df["close"], 8)
        first_cross = next(i for i in range(1, len(df)) if fast[i] < slow[i] and fast[i - 1] >= slow[i - 1])
        assert df["exit_long"][first_cross] == 1

    def test_tag_carries_atr_stop_distance(self):
        close = list(np.linspace(100, 160, 60)) + [150, 145, 150, 158, 165]
        df = trend_signals(frame(close), **TREND)
        a = atr(df, 3)
        for i in df.index[df["enter_long"] == 1]:
            assert parse_stop_dist(df["enter_tag"][i]) == pytest.approx(3.0 * a[i], rel=1e-6)


def dip_series():
    # yüksəliş → yan xətt (RSI neytrallaşır) → kəskin dip (185) → bərpa (201)
    return list(np.linspace(100, 200, 100)) + [200, 201] * 10 + [198, 196, 185, 192, 196, 201]


class TestMeanRev:
    def test_no_entry_below_trend_ema(self):
        # davamlı düşüş: qiymət trend EMA-dan aşağıdır → dip olsa da giriş yoxdur
        close = list(np.linspace(200, 120, 150)) + [110, 100, 95]
        out = meanrev_signals(frame(close), **MR)
        assert out["enter_long"].sum() == 0

    def test_entry_exactly_at_dip_and_conditions_hold(self):
        df = meanrev_signals(frame(dip_series()), **MR)
        entries = df.index[df["enter_long"] == 1].tolist()
        dip = len(df) - 4
        assert entries == [dip]
        _, _, lower = bollinger(df["close"], 20, 2.0)
        assert df["close"][dip] < lower[dip]
        assert rsi(df["close"], 14)[dip] < 40.0
        assert df["close"][dip] > ema(df["close"], 100)[dip]
        assert parse_stop_dist(df["enter_tag"][dip]) == pytest.approx(2.0 * atr(df, 14)[dip], rel=1e-6)

    def test_exit_when_back_above_middle_band(self):
        df = meanrev_signals(frame(dip_series()), **MR)
        mid, _, _ = bollinger(df["close"], 20, 2.0)
        last = len(df) - 1
        assert df["exit_long"][last] == 1
        exits = df["exit_long"] == 1
        assert (df["close"][exits] > mid[exits]).all()

    def test_bb_period_too_short_is_rejected(self):
        # n şamlıq pəncərədə nöqtə ortadan ən çox sqrt(n-1) std uzaqlaşır:
        # n <= 5 və 2 std ilə "aşağı zolaqdan aşağı" riyazi olaraq mümkün deyil
        with pytest.raises(ValueError):
            meanrev_signals(frame(dip_series()), **{**MR, "bb_period": 5})
