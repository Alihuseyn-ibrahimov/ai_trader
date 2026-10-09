"""OOS qiymətləndirməsi — Go/No-Go qərarı bu koddan çıxır, ona görə hər meyar testlidir."""

import math

import pandas as pd
import pytest

from oos_eval import evaluate, mtm_equity, profit_factor, yearly_tax

FEE = 0.0015


def trade(pair, open_, close, open_rate, close_rate, stake, profit):
    return {
        "pair": pair,
        "open_date": pd.Timestamp(open_, tz="UTC"),
        "close_date": pd.Timestamp(close, tz="UTC"),
        "open_rate": open_rate,
        "close_rate": close_rate,
        "amount": stake / open_rate,
        "stake_amount": stake,
        "fee_open": FEE,
        "fee_close": FEE,
        "profit_abs": profit,
    }


def daily(pair_closes, start="2025-01-01"):
    dates = pd.date_range(start, periods=len(pair_closes), freq="1D", tz="UTC")
    return pd.DataFrame({"date": dates, "close": pair_closes})


class TestTax:
    def test_tax_per_calendar_year_only_on_positive_years(self):
        t = pd.DataFrame([
            trade("BTC/USDT", "2025-01-01", "2025-02-01", 100, 110, 100, 50),
            trade("BTC/USDT", "2025-03-01", "2025-04-01", 100, 90, 100, -20),   # 2025: +30
            trade("BTC/USDT", "2026-01-01", "2026-02-01", 100, 90, 100, -40),   # 2026: −40 → 0
        ])
        assert yearly_tax(t, 0.14) == pytest.approx(0.14 * 30)

    def test_no_carry_forward_of_losses(self):
        # ehtiyatlı fərziyyə: zərər növbəti ilə keçirilmir
        t = pd.DataFrame([
            trade("BTC/USDT", "2025-01-01", "2025-02-01", 100, 90, 100, -100),
            trade("BTC/USDT", "2026-01-01", "2026-02-01", 100, 110, 100, 60),
        ])
        assert yearly_tax(t, 0.14) == pytest.approx(0.14 * 60)


class TestProfitFactor:
    def test_ratio(self):
        t = pd.DataFrame([
            trade("BTC/USDT", "2025-01-01", "2025-01-02", 1, 1, 1, 30),
            trade("BTC/USDT", "2025-01-03", "2025-01-04", 1, 1, 1, -10),
        ])
        assert profit_factor(t) == pytest.approx(3.0)

    def test_no_losses_is_inf_and_no_trades_is_zero(self):
        t = pd.DataFrame([trade("BTC/USDT", "2025-01-01", "2025-01-02", 1, 1, 1, 5)])
        assert math.isinf(profit_factor(t))
        assert profit_factor(t.iloc[0:0]) == 0.0


class TestMtmEquity:
    def test_open_position_marked_to_daily_close(self):
        # 1000 kapital; 2025-01-01 00:00-da 100-dən 500 USDT-lik alış (5 vahid),
        # 2025-01-03-də bağlanır. Gün sonu qiymətləri: 80 (1-ci gün), 120 (2-ci gün)
        t = pd.DataFrame([trade("BTC/USDT", "2025-01-01", "2025-01-03", 100, 120, 500, 98.35)])
        prices = {"BTC/USDT": daily([80.0, 120.0, 120.0])}
        eq = mtm_equity(t, prices, 1000.0, "2025-01-01", "2025-01-04")
        unreal_day1 = 5 * 80 * (1 - FEE) - 500 * (1 + FEE)
        assert eq.iloc[0] == pytest.approx(1000.0)                  # başlanğıc
        assert eq.loc[pd.Timestamp("2025-01-02", tz="UTC")] == pytest.approx(1000 + unreal_day1)
        assert eq.iloc[-1] == pytest.approx(1000 + 98.35)            # bağlandıqdan sonra reallaşmış

    def test_drawdown_visible_only_in_mtm(self):
        # bağlanmış əməliyyatlar üzrə DD 0-dır, amma açıq mövqe 40% düşüb
        t = pd.DataFrame([trade("BTC/USDT", "2025-01-01", "2025-01-03", 100, 101, 500, 1.0)])
        prices = {"BTC/USDT": daily([60.0, 101.0, 101.0])}
        eq = mtm_equity(t, prices, 1000.0, "2025-01-01", "2025-01-04")
        assert eq.min() < 820


class TestEvaluate:
    base = dict(bh_net_return=-0.154, bh_max_drawdown=0.60, is_profit_factor=3.17)

    def call(self, **m):
        metrics = dict(n_trades=40, max_drawdown=0.12, profit_factor=2.0, net_return=0.08)
        metrics.update(m)
        return evaluate(metrics, **self.base)

    def test_all_pass_is_go(self):
        r = self.call()
        assert all(r["criteria"].values())
        assert r["go"] is True

    @pytest.mark.parametrize(
        "override,failed",
        [
            ({"n_trades": 29}, "1_trades"),
            ({"max_drawdown": 0.20}, "2_drawdown"),          # sərhəd: < 20% tələb olunur
            ({"profit_factor": 1.2}, "3_profit_factor"),     # sərhəd: > 1.2
            ({"net_return": -0.20}, "4_vs_baseline"),
            ({"profit_factor": 1.5}, "5_is_vs_oos"),         # 1.5 < 0.5 × 3.17
            ({"net_return": 0.0}, "6_positive"),
        ],
    )
    def test_each_criterion_can_fail_alone(self, override, failed):
        r = self.call(**override)
        assert r["criteria"][failed] is False
        assert r["go"] is False

    def test_baseline_alternative_clause(self):
        # baseline müsbət olsa: B&H-dən az, amma ≥70%-i və DD yarıdan az → keçir
        r = evaluate(dict(n_trades=40, max_drawdown=0.10, profit_factor=2.0, net_return=0.75),
                     bh_net_return=1.0, bh_max_drawdown=0.30, is_profit_factor=3.17)
        assert r["criteria"]["4_vs_baseline"] is True
