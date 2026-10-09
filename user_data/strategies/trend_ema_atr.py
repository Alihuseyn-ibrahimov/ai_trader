"""Strategiya A — TrendEmaAtr (4h): trend izləmə, EMA 50/200 + ATR trailing stop.

Qaydalar `signals/trend.py`-dadır. Parametrlər Faza 0 planında sabitlənib və
yalnız IS datasına baxaraq dəyişdirilə bilər (OOS-a baxıb dəyişmək qadağandır).
Düşüş trendində (EMA50 < EMA200) giriş yoxdur — pul USDT-də qalır.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from risk_managed import RiskManagedStrategy  # noqa: E402
from signals.trend import trend_signals  # noqa: E402


class TrendEmaAtr(RiskManagedStrategy):
    timeframe = "4h"
    params = dict(ema_fast=50, ema_slow=200, atr_period=14, atr_mult=3.0)

    use_custom_stoploss = True
    atr_trailing = True            # stop ən yüksək qiymətin 3×ATR arxasınca gedir
    stoploss = -0.15               # yalnız ehtiyat (backstop); əsl stop ATR-dır
    minimal_roi = {"0": 100}       # ROI söndürülüb: çıxış siqnal və ya stop ilə
    startup_candle_count = 400     # EMA200 sabitləşsin
    process_only_new_candles = True

    def populate_indicators(self, dataframe, metadata):
        sig = trend_signals(dataframe, **self.params)
        dataframe["sig_enter"] = sig["enter_long"]
        dataframe["sig_exit"] = sig["exit_long"]
        dataframe["sig_tag"] = sig["enter_tag"]
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        entry = dataframe["sig_enter"] == 1
        dataframe.loc[entry, "enter_long"] = 1
        dataframe.loc[entry, "enter_tag"] = dataframe.loc[entry, "sig_tag"]
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[dataframe["sig_exit"] == 1, "exit_long"] = 1
        return dataframe
