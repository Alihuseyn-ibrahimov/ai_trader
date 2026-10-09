import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    """Wilder ATR. True range əvvəlki bağlanışdan olan boşluğu da nəzərə alır."""
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [df["high"] - df["low"], (df["high"] - prev_close).abs(), (df["low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder RSI."""
    delta = series.diff().fillna(0.0)
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100 - 100 / (1 + gain / loss)
    out = out.where(loss != 0, 100.0)
    return out.where((gain != 0) | (loss != 0), 50.0)


def bollinger(series: pd.Series, period: int, num_std: float):
    """(orta, yuxarı, aşağı). Standart sapma ddof=0 — TA-Lib ilə eyni."""
    mid = series.rolling(period).mean()
    std = series.rolling(period).std(ddof=0)
    return mid, mid + num_std * std, mid - num_std * std
