"""Risk modulu — Faza 2-3-də canlı botun vetosu da bu koddur. Səhv = real pul."""

import pytest

from risk import (
    RiskConfig,
    TradeDecision,
    check_entry,
    daily_loss_breached,
    floor_breached,
    position_size,
)


class TestRiskConfig:
    def test_defaults_are_conservative(self):
        c = RiskConfig()
        assert c.risk_per_trade == 0.01
        assert c.daily_loss_limit == 0.03
        assert c.max_open_trades == 2

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"risk_per_trade": 0},
            {"risk_per_trade": 0.06},          # sərt tavan 5%
            {"risk_per_trade": -0.01},
            {"daily_loss_limit": 0},
            {"daily_loss_limit": 0.2},         # sərt tavan 10%
            {"floor_ratio": 1.0},              # alt xətt başlanğıc kapitala bərabər ola bilməz
            {"floor_ratio": -0.1},
            {"max_open_trades": 0},
        ],
    )
    def test_rejects_unsafe_values(self, kwargs):
        with pytest.raises(ValueError):
            RiskConfig(**kwargs)

    def test_is_immutable(self):
        c = RiskConfig()
        with pytest.raises(AttributeError):
            c.risk_per_trade = 0.5

    def test_from_dict_ignores_nothing_silently(self):
        with pytest.raises(ValueError):
            RiskConfig.from_dict({"risk_per_trade": 0.01, "risk_per_trad": 0.5})  # yazı səhvi


class TestPositionSize:
    def test_risk_one_percent_of_equity(self):
        # 1000 kapital, 1% = 10 risk; giriş 100, stop 95 → vahid riski 5 → 2 vahid → 200 stake
        assert position_size(1000, entry=100, stop=95, risk_pct=0.01) == pytest.approx(200)

    def test_loss_at_stop_equals_risk_amount(self):
        stake = position_size(1000, entry=100, stop=95, risk_pct=0.01)
        loss = stake / 100 * (100 - 95)
        assert loss == pytest.approx(10)

    def test_fees_reduce_size_so_total_loss_stays_within_risk(self):
        fee = 0.0015
        stake = position_size(1000, entry=100, stop=95, risk_pct=0.01, fee=fee)
        qty = stake / 100
        total_loss = qty * (100 - 95) + qty * 100 * fee + qty * 95 * fee
        assert total_loss == pytest.approx(10)
        assert stake < 200

    def test_capped_at_equity_no_leverage(self):
        # çox dar stop → nəzəri ölçü kapitaldan böyük; spot-da leverage yoxdur
        assert position_size(1000, entry=100, stop=99.9, risk_pct=0.01) == pytest.approx(1000)

    def test_floor_limits_loss(self):
        # kapital 1000, alt xətt 995 → stopda itki ən çox 5 ola bilər (1% = 10 yox)
        stake = position_size(1000, entry=100, stop=95, risk_pct=0.01, floor=995)
        assert stake / 100 * 5 == pytest.approx(5)

    def test_at_or_below_floor_returns_zero(self):
        assert position_size(995, entry=100, stop=95, risk_pct=0.01, floor=995) == 0.0
        assert position_size(900, entry=100, stop=95, risk_pct=0.01, floor=995) == 0.0

    @pytest.mark.parametrize(
        "equity,entry,stop",
        [(0, 100, 95), (-5, 100, 95), (1000, 100, 100), (1000, 100, 105), (1000, 0, -1), (1000, 100, -1)],
    )
    def test_invalid_inputs_raise(self, equity, entry, stop):
        with pytest.raises(ValueError):
            position_size(equity, entry=entry, stop=stop, risk_pct=0.01)


class TestBreaches:
    def test_daily_loss(self):
        assert daily_loss_breached(1000, 970, limit=0.03) is True    # tam 3% → dayan
        assert daily_loss_breached(1000, 971, limit=0.03) is False
        assert daily_loss_breached(1000, 1100, limit=0.03) is False  # qazanc

    def test_daily_loss_invalid_start(self):
        with pytest.raises(ValueError):
            daily_loss_breached(0, 10, limit=0.03)

    def test_floor(self):
        assert floor_breached(700, floor=700) is True
        assert floor_breached(699, floor=700) is True
        assert floor_breached(701, floor=700) is False


class TestCheckEntry:
    cfg = RiskConfig(risk_per_trade=0.01, daily_loss_limit=0.03, floor_ratio=0.7, max_open_trades=2)

    def call(self, **over):
        state = dict(equity=1000, start_equity=1000, day_start_equity=1000, open_trades=0)
        state.update(over)
        return check_entry(config=self.cfg, **state)

    def test_allows_normal_entry(self):
        d = self.call()
        assert d == TradeDecision(True, "ok")

    def test_floor_veto_has_priority(self):
        d = self.call(equity=700, day_start_equity=800)
        assert not d.allowed and d.reason == "floor"

    def test_daily_loss_veto(self):
        d = self.call(equity=960, day_start_equity=1000)
        assert not d.allowed and d.reason == "daily_loss"

    def test_max_open_trades_veto(self):
        d = self.call(open_trades=2)
        assert not d.allowed and d.reason == "max_open_trades"

    def test_floor_is_relative_to_start_equity(self):
        assert check_entry(config=self.cfg, equity=1400, start_equity=2000,
                           day_start_equity=1400, open_trades=0).reason == "floor"
