"""RiskSmokeTest — ticarət strategiyası DEYİL. Yalnız risk mexanikasının real
backtest-də işlədiyini yoxlamaq üçündür (mövqe ölçüsü, vetolar, kill switch).

Qayda qəsdən primitivdir: qiymət 3 şam ardıcıl qalxıbsa al, 3 şam ardıcıl
düşübsə sat. Nəticəsi strategiya qiymətləndirməsində İSTİFADƏ OLUNMUR.
Yalnız IS dövründə işlədilir.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from risk_managed import RiskManagedStrategy  # noqa: E402


class RiskSmokeTest(RiskManagedStrategy):
    timeframe = "1h"
    stoploss = -0.03
    minimal_roi = {"0": 0.04}
    startup_candle_count = 5

    def populate_indicators(self, dataframe, metadata):
        up = dataframe["close"] > dataframe["close"].shift(1)
        dataframe["up3"] = up & up.shift(1, fill_value=False) & up.shift(2, fill_value=False)
        down = dataframe["close"] < dataframe["close"].shift(1)
        dataframe["down3"] = down & down.shift(1, fill_value=False) & down.shift(2, fill_value=False)
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        dataframe.loc[dataframe["up3"], "enter_long"] = 1
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        dataframe.loc[dataframe["down3"], "exit_long"] = 1
        return dataframe
