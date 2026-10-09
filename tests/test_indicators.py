import numpy as np
import pandas as pd
import pytest

from signals.indicators import atr, bollinger, ema, rsi


def test_ema_constant_series():
    s = pd.Series([5.0] * 10)
    assert ema(s, 3).tolist() == pytest.approx([5.0] * 10)


def test_ema_recursion():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    a = 2 / (3 + 1)
    exp = [1.0]
    for x in s[1:]:
        exp.append(a * x + (1 - a) * exp[-1])
    assert ema(s, 3).tolist() == pytest.approx(exp)


def test_atr_constant_true_range():
    # hər şamda high-low = 2, boşluq yoxdur → ATR 2-yə yaxınlaşır
    n = 50
    close = pd.Series(np.full(n, 100.0))
    df = pd.DataFrame({"high": close + 1, "low": close - 1, "close": close})
    assert atr(df, 14).iloc[-1] == pytest.approx(2.0)


def test_atr_uses_gap_from_previous_close():
    df = pd.DataFrame({"high": [101.0, 121.0], "low": [99.0, 119.0], "close": [100.0, 120.0]})
    # 2-ci şamın TR-i = max(2, |121-100|, |119-100|) = 21
    tr = atr(df, 1)
    assert tr.iloc[1] == pytest.approx(21.0)


def test_rsi_extremes():
    up = pd.Series(np.arange(1.0, 40.0))
    down = pd.Series(np.arange(40.0, 1.0, -1))
    assert rsi(up, 14).iloc[-1] == pytest.approx(100.0)
    assert rsi(down, 14).iloc[-1] == pytest.approx(0.0)


def test_rsi_balanced_is_50():
    s = pd.Series([100.0, 101.0] * 50)
    assert rsi(s, 14).iloc[-1] == pytest.approx(50.0, abs=2.0)


def test_bollinger_population_std():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    mid, upper, lower = bollinger(s, 4, 2.0)
    std = np.std([1, 2, 3, 4])  # ddof=0, TA-Lib kimi
    assert mid.iloc[-1] == pytest.approx(2.5)
    assert upper.iloc[-1] == pytest.approx(2.5 + 2 * std)
    assert lower.iloc[-1] == pytest.approx(2.5 - 2 * std)
