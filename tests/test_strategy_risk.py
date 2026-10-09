"""RiskManagedStrategy — Freqtrade callback-ları risk modulu ilə düzgün bağlanıbmı.

Yalnız Freqtrade quraşdırılmış mühitdə işləyir (konteyner). Lokal venv-də skip.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("freqtrade")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "user_data" / "strategies"))

from freqtrade.strategy import stoploss_from_absolute  # noqa: E402
from risk import position_size  # noqa: E402
from risk_managed import ASSUMED_FEE, RiskManagedStrategy  # noqa: E402

T0 = datetime(2023, 5, 1, 0, 0, tzinfo=timezone.utc)
T0_LATER = datetime(2023, 5, 1, 15, 0, tzinfo=timezone.utc)
T1 = datetime(2023, 5, 2, 0, 0, tzinfo=timezone.utc)


class Wallet:
    def __init__(self, equity, start=1000.0):
        self.equity, self.start = equity, start

    def get_total_stake_amount(self):
        return self.equity

    def get_starting_balance(self):
        return self.start


class Concrete(RiskManagedStrategy):
    stoploss = -0.05
    timeframe = "1h"

    def populate_indicators(self, dataframe, metadata):
        return dataframe

    def populate_entry_trend(self, dataframe, metadata):
        return dataframe

    def populate_exit_trend(self, dataframe, metadata):
        return dataframe


def make(equity=1000.0, open_trades=0, risk=None):
    cfg = {
        "stake_currency": "USDT",
        "timeframe": "1h",
        "ai_risk": risk or {"risk_per_trade": 0.01, "daily_loss_limit": 0.03,
                            "floor_ratio": 0.7, "max_open_trades": 2},
    }
    s = Concrete(cfg)
    s.wallets = Wallet(equity)
    s._open_trade_count = lambda: open_trades
    s.bot_start()
    s.bot_loop_start(current_time=T0)
    return s


def stake(s, rate=100.0, max_stake=10_000.0, entry_tag=None):
    return s.custom_stake_amount(
        pair="BTC/USDT", current_time=T0_LATER, current_rate=rate, proposed_stake=999.0,
        min_stake=5.0, max_stake=max_stake, leverage=1.0, entry_tag=entry_tag, side="long",
    )


def confirm(s):
    return s.confirm_trade_entry(
        pair="BTC/USDT", order_type="limit", amount=1.0, rate=100.0, time_in_force="GTC",
        current_time=T0_LATER, entry_tag=None, side="long",
    )


class TestStake:
    def test_uses_risk_module_with_fee_and_floor(self):
        s = make()
        expected = position_size(1000, 100, 95, 0.01, fee=ASSUMED_FEE, floor=700)
        assert stake(s) == pytest.approx(expected)
        assert stake(s) < 200  # proposed_stake (999) istifadə olunmur

    def test_respects_max_stake(self):
        assert stake(make(), max_stake=50.0) == pytest.approx(50.0)

    def test_fail_closed_on_error(self):
        s = make()
        s.stop_price = lambda pair, rate, entry_tag=None: rate * 2  # səhv: stop girişdən yuxarı
        assert stake(s) == 0.0

    def test_zero_at_floor(self):
        assert stake(make(equity=700.0)) == 0.0


    def test_stop_distance_from_entry_tag(self):
        # ATR stopu: tag-dakı məsafə (10) → stop 90, sabit stoploss (-5%) yox
        expected = position_size(1000, 100, 90, 0.01, fee=ASSUMED_FEE, floor=700)
        assert stake(make(), entry_tag="trend|sd=10") == pytest.approx(expected)


class TestCustomStoploss:
    def call(self, s, trade, rate):
        return s.custom_stoploss("BTC/USDT", trade, T0_LATER, rate, 0.0, after_fill=False)

    def test_fixed_atr_stop_from_tag(self):
        s = make()
        trade = SimpleNamespace(open_rate=100.0, max_rate=120.0, enter_tag="meanrev|sd=10")
        assert self.call(s, trade, 110.0) == pytest.approx(stoploss_from_absolute(90.0, 110.0))

    def test_trailing_atr_stop_follows_max_rate(self):
        s = make()
        s.atr_trailing = True
        trade = SimpleNamespace(open_rate=100.0, max_rate=120.0, enter_tag="trend|sd=10")
        # stop = max(100-10, 120-10) = 110
        assert self.call(s, trade, 115.0) == pytest.approx(stoploss_from_absolute(110.0, 115.0))

    def test_without_tag_keeps_static_stoploss(self):
        trade = SimpleNamespace(open_rate=100.0, max_rate=120.0, enter_tag=None)
        assert self.call(make(), trade, 110.0) is None


class TestConfirmEntry:
    def test_allows_normal(self):
        assert confirm(make()) is True

    def test_daily_loss_veto_and_counter(self):
        s = make()
        s.wallets.equity = 960.0
        assert confirm(s) is False
        assert s.risk_vetoes["daily_loss"] == 1

    def test_new_day_resets_daily_start(self):
        s = make()
        s.wallets.equity = 960.0
        s.bot_loop_start(current_time=T1)
        assert confirm(s) is True

    def test_floor_veto(self):
        s = make()
        s.wallets.equity = 690.0
        s.bot_loop_start(current_time=T1)
        assert confirm(s) is False
        assert s.risk_vetoes["floor"] == 1

    def test_max_open_trades_veto(self):
        assert confirm(make(open_trades=2)) is False

    def test_fail_closed_on_error(self):
        s = make()
        s._open_trade_count = lambda: (_ for _ in ()).throw(RuntimeError("db"))
        assert confirm(s) is False


class TestKillSwitch:
    def test_exits_when_realized_plus_unrealized_hits_floor(self):
        s = make(equity=720.0)
        trade = SimpleNamespace(stake_amount=250.0)
        # 720 + 250 * (-0.1) = 695 <= 700
        assert s.custom_exit("BTC/USDT", trade, T0_LATER, 90.0, -0.1) == "floor_kill_switch"

    def test_no_exit_above_floor(self):
        s = make(equity=1000.0)
        trade = SimpleNamespace(stake_amount=250.0)
        assert s.custom_exit("BTC/USDT", trade, T0_LATER, 90.0, -0.1) is None


class TestConfig:
    def test_typo_in_risk_config_fails_start(self):
        with pytest.raises(ValueError):
            make(risk={"risk_per_trad": 0.01})

    def test_protections_present(self):
        names = {p["method"] for p in make().protections}
        assert {"StoplossGuard", "MaxDrawdown", "CooldownPeriod"} <= names

    def test_no_shorting(self):
        assert RiskManagedStrategy.can_short is False
