import pandas as pd
import pytest

from data_quality import (
    check_file,
    count_duplicates,
    find_gaps,
    ohlc_violations,
    slice_period,
    zero_volume,
)


def make_df(dates, open_=100.0, high=110.0, low=90.0, close=105.0, volume=1.0):
    return pd.DataFrame(
        {
            "date": pd.to_datetime(dates, utc=True),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


def hourly(start, periods):
    return pd.date_range(start, periods=periods, freq="1h", tz="UTC")


class TestFindGaps:
    def test_no_gaps(self):
        df = make_df(hourly("2023-01-01", 5))
        assert find_gaps(df, "1h") == []

    def test_single_missing_candle(self):
        dates = list(hourly("2023-01-01", 5))
        del dates[2]  # 02:00 yoxdur
        gaps = find_gaps(make_df(dates), "1h")
        assert gaps == [(pd.Timestamp("2023-01-01 02:00", tz="UTC"), 1)]

    def test_multi_candle_gap_counted_once_with_size(self):
        dates = list(hourly("2023-01-01", 10))
        dates = dates[:3] + dates[6:]  # 03:00, 04:00, 05:00 yoxdur
        gaps = find_gaps(make_df(dates), "1h")
        assert gaps == [(pd.Timestamp("2023-01-01 03:00", tz="UTC"), 3)]

    def test_4h_and_1d_timeframes(self):
        d4 = pd.date_range("2023-01-01", periods=4, freq="4h", tz="UTC").delete(1)
        assert find_gaps(make_df(d4), "4h") == [
            (pd.Timestamp("2023-01-01 04:00", tz="UTC"), 1)
        ]
        d1 = pd.date_range("2023-01-01", periods=4, freq="1D", tz="UTC").delete(2)
        assert find_gaps(make_df(d1), "1d") == [
            (pd.Timestamp("2023-01-03", tz="UTC"), 1)
        ]

    def test_unknown_timeframe_raises(self):
        with pytest.raises(ValueError):
            find_gaps(make_df(hourly("2023-01-01", 3)), "7x")


class TestOtherChecks:
    def test_duplicates(self):
        dates = list(hourly("2023-01-01", 3)) + [pd.Timestamp("2023-01-01 01:00", tz="UTC")]
        assert count_duplicates(make_df(dates)) == 1

    def test_ohlc_violations(self):
        df = make_df(hourly("2023-01-01", 4))
        df.loc[0, "high"] = 99.0   # high < close (105)
        df.loc[1, "low"] = 101.0   # low > open (100)
        df.loc[2, "close"] = 0.0   # qiymət <= 0
        assert ohlc_violations(df) == 3

    def test_zero_volume(self):
        df = make_df(hourly("2023-01-01", 3))
        df.loc[1, "volume"] = 0.0
        assert zero_volume(df) == 1


class TestSlicePeriod:
    def test_half_open_interval_matches_freqtrade_timerange(self):
        df = make_df(pd.date_range("2023-12-30", periods=4, freq="1D", tz="UTC"))
        out = slice_period(df, "2023-12-31", "2024-01-02")
        # başlanğıc daxil, son xaric (Freqtrade --timerange kimi)
        assert list(out["date"].dt.strftime("%Y-%m-%d")) == ["2023-12-31", "2024-01-01"]


def test_check_file_uses_given_period(tmp_path):
    dates = pd.date_range("2019-12-01", "2020-01-10", freq="1D", tz="UTC")
    path = tmp_path / "BTC_USDT-1d.feather"
    make_df(dates).to_feather(path)
    r = check_file(path, "1d", "2020-01-01", "2020-01-06")
    assert r["expected"] == 5 and r["rows"] == 5
