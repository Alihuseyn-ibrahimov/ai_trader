"""Strategiya A — trend izləmə (EMA fast/slow + ATR stop).

Giriş: yüksələn trend (fast EMA > slow EMA) və qiymət fast EMA-nı aşağıdan yuxarı
keçir (geri çəkilmədən sonra bərpa).
Çıxış siqnalı: fast EMA slow EMA-nı yuxarıdan aşağı keçir (trend bitdi).
Stop: girişdə atr_mult × ATR məsafəsi (enter_tag-da), strategiyada trailing.
"""

import pandas as pd

from signals.indicators import atr, ema
from signals.tags import make_tag


def trend_signals(df: pd.DataFrame, ema_fast: int, ema_slow: int, atr_period: int,
                  atr_mult: float) -> pd.DataFrame:
    df = df.copy()
    fast, slow = ema(df["close"], ema_fast), ema(df["close"], ema_slow)
    stop_dist = atr_mult * atr(df, atr_period)

    entry = (fast > slow) & (df["close"] > fast) & (df["close"].shift(1) <= fast.shift(1))
    entry &= stop_dist > 0
    exit_ = (fast < slow) & (fast.shift(1) >= slow.shift(1))

    df["enter_long"] = entry.astype(int)
    df["exit_long"] = exit_.astype(int)
    df["enter_tag"] = None
    df.loc[entry, "enter_tag"] = [make_tag("trend", d) for d in stop_dist[entry]]
    return df
