import math

import pandas as pd
import pytest

from baseline import annual_volatility, buy_and_hold, max_drawdown, portfolio_equity


def daily(closes, opens=None, start="2023-01-01"):
    dates = pd.date_range(start, periods=len(closes), freq="1D", tz="UTC")
    opens = opens if opens is not None else closes
    return pd.DataFrame({"date": dates, "open": opens, "close": closes})


class TestMaxDrawdown:
    def test_monotonic_up_is_zero(self):
        assert max_drawdown(pd.Series([1.0, 1.1, 1.2])) == 0.0

    def test_peak_to_trough(self):
        # pik 2.0 → dib 1.0 = 50%, sonradan bərpa DD-ni dəyişmir
        assert max_drawdown(pd.Series([1.0, 2.0, 1.5, 1.0, 3.0])) == pytest.approx(0.5)


class TestBuyAndHold:
    def test_entry_at_first_open_exit_at_last_close(self):
        df = daily(closes=[110.0, 120.0, 150.0], opens=[100.0, 110.0, 120.0])
        r = buy_and_hold(df, fee=0.0, tax=0.0)
        assert r["gross_return"] == pytest.approx(0.5)
        assert r["net_return"] == pytest.approx(0.5)

    def test_fee_both_sides_and_tax_only_on_profit(self):
        df = daily(closes=[100.0, 200.0], opens=[100.0, 150.0])
        r = buy_and_hold(df, fee=0.01, tax=0.14)
        after_fees = 0.99 * 2.0 * 0.99 - 1          # 0.9602
        assert r["net_return"] == pytest.approx(after_fees * (1 - 0.14))

    def test_no_tax_on_loss(self):
        df = daily(closes=[100.0, 50.0], opens=[100.0, 60.0])
        r = buy_and_hold(df, fee=0.0, tax=0.14)
        assert r["net_return"] == pytest.approx(-0.5)

    def test_drawdown_uses_entry_price_as_start(self):
        # giriş 100-dən, ilk close 80 → 20% DD olmalıdır
        df = daily(closes=[80.0, 120.0], opens=[100.0, 80.0])
        assert buy_and_hold(df, fee=0.0, tax=0.0)["max_drawdown"] == pytest.approx(0.2)

    def test_empty_period_raises(self):
        with pytest.raises(ValueError):
            buy_and_hold(daily(closes=[])[0:0], fee=0.0, tax=0.0)


class TestPortfolioAndVol:
    def test_equal_weight_no_rebalance(self):
        a = daily(closes=[200.0], opens=[100.0])   # x2
        b = daily(closes=[50.0], opens=[100.0])    # x0.5
        eq = portfolio_equity([a, b], [0.5, 0.5])
        assert list(eq) == pytest.approx([1.0, 1.25])

    def test_weights_must_sum_to_one(self):
        a = daily(closes=[1.0])
        with pytest.raises(ValueError):
            portfolio_equity([a, a], [0.5, 0.6])

    def test_constant_price_zero_vol(self):
        assert annual_volatility(pd.Series([1.0] * 10)) == 0.0

    def test_annualised_with_365(self):
        s = pd.Series([1.0, 1.1, 1.0, 1.1, 1.0])
        logret = pd.Series([math.log(1.1), math.log(1 / 1.1)] * 2)
        assert annual_volatility(s) == pytest.approx(logret.std() * math.sqrt(365))
