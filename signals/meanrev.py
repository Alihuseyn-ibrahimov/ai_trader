"""Strategiya B — qiymətin ortaya qayıtması (RSI + Bollinger, trend filtri ilə).

Giriş: qiymət aşağı Bollinger zolağından aşağı, RSI(14) < rsi_entry və qiymət
trend EMA-dan yuxarıdır (yalnız ümumi yüksəliş fonunda dib alınır).
Çıxış siqnalı: qiymət orta zolaqdan (SMA) yuxarı qayıdır.
Stop: girişdə atr_mult × ATR(14) məsafəsi (enter_tag-da), sabit (trailing yox).
Sabit, tənzimlənməyən dəyərlər: RSI dövrü 14, Bollinger 2.0 std, ATR dövrü 14.
"""

import pandas as pd

from signals.indicators import atr, bollinger, ema, rsi
from signals.tags import make_tag

RSI_PERIOD = 14
BB_STD = 2.0
ATR_PERIOD = 14


def meanrev_signals(df: pd.DataFrame, bb_period: int, rsi_entry: float, atr_mult: float,
                    trend_ema: int) -> pd.DataFrame:
    # n şamlıq pəncərədə nöqtə ortadan ən çox sqrt(n-1) std uzaqlaşa bilər
    if (bb_period - 1) ** 0.5 <= BB_STD:
        raise ValueError(f"bb_period={bb_period} ilə qiymət aşağı zolaqdan aşağı düşə bilməz")
    df = df.copy()
    mid, _, lower = bollinger(df["close"], bb_period, BB_STD)
    r = rsi(df["close"], RSI_PERIOD)
    trend = ema(df["close"], trend_ema)
    stop_dist = atr_mult * atr(df, ATR_PERIOD)

    entry = (df["close"] < lower) & (r < rsi_entry) & (df["close"] > trend) & (stop_dist > 0)
    exit_ = df["close"] > mid

    df["enter_long"] = entry.astype(int)
    df["exit_long"] = exit_.astype(int)
    df["enter_tag"] = None
    df.loc[entry, "enter_tag"] = [make_tag("meanrev", d) for d in stop_dist[entry]]
    return df
