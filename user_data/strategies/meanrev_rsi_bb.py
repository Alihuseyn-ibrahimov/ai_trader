"""Strategiya B — MeanRevRsiBb (1h): qiymətin ortaya qayıtması, RSI + Bollinger.

Qaydalar `signals/meanrev.py`-dadır. Yalnız qiymət EMA200-dən yuxarı olanda
(ümumi yüksəliş fonunda) dib alınır. Stop: 2×ATR, sabit (trailing yox).
Parametrlər Faza 0 planında sabitlənib.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from risk_managed import RiskManagedStrategy  # noqa: E402
from signals.meanrev import meanrev_signals  # noqa: E402


class MeanRevRsiBb(RiskManagedStrategy):
    timeframe = "1h"
    params = dict(bb_period=20, rsi_entry=30.0, atr_mult=2.0, trend_ema=200)

    use_custom_stoploss = True
    atr_trailing = False
    stoploss = -0.10               # yalnız ehtiyat (backstop); əsl stop ATR-dır
    minimal_roi = {"0": 100}       # ROI söndürülüb: çıxış siqnal və ya stop ilə
    startup_candle_count = 400
    process_only_new_candles = True

    def populate_indicators(self, dataframe, metadata):
        sig = meanrev_signals(dataframe, **self.params)
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
