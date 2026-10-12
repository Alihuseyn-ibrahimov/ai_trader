import pandas as pd
import pytest

from tax_report import (
    CSV_COLUMNS,
    RateBook,
    journal,
    parse_cbar_usd,
    year_summary,
)

T = lambda s: pd.Timestamp(s, tz="UTC")  # noqa: E731


def trades(rows):
    base = {"pair": "BTC/USDT", "fee_open": 0.001, "fee_close": 0.001, "is_open": False}
    df = pd.DataFrame([{**base, **r} for r in rows])
    for c in ("open_date", "close_date"):
        df[c] = pd.to_datetime(df[c], utc=True)
    return df


def profit(amount, o, c, fo=0.001, fc=0.001):
    # Freqtrade-in profit_abs düsturu: satış dəyəri − alış dəyəri (komissiyalar daxil)
    return amount * c * (1 - fc) - amount * o * (1 + fo)


WIN = dict(open_date="2026-03-01 10:00", close_date="2026-03-10 10:00",
           amount=0.01, open_rate=60000.0, close_rate=66000.0, profit_abs=profit(0.01, 60000, 66000))
LOSS = dict(open_date="2026-04-01 10:00", close_date="2026-04-05 10:00",
            amount=0.01, open_rate=66000.0, close_rate=63000.0, profit_abs=profit(0.01, 66000, 63000))
RATES = RateBook({pd.Timestamp("2026-03-01").date(): 1.70, pd.Timestamp("2026-03-10").date(): 1.70,
                  pd.Timestamp("2026-04-01").date(): 1.70, pd.Timestamp("2026-04-05").date(): 1.70})


# --- jurnal ------------------------------------------------------------------------

def test_journal_legs_and_pnl_by_hand():
    j = journal(trades([WIN]), RATES)
    r = j.iloc[0]
    assert r["cost_usdt"] == pytest.approx(0.01 * 60000 * 1.001)          # 600.60
    assert r["proceeds_usdt"] == pytest.approx(0.01 * 66000 * 0.999)      # 659.34
    assert r["pnl_usdt"] == pytest.approx(58.74)
    assert r["cost_azn"] == pytest.approx(600.60 * 1.70)
    assert r["proceeds_azn"] == pytest.approx(659.34 * 1.70)
    assert r["pnl_azn"] == pytest.approx(58.74 * 1.70)


def test_journal_pnl_matches_freqtrade_profit():
    j = journal(trades([WIN, LOSS]), RATES)
    assert j["pnl_usdt"].tolist() == pytest.approx([WIN["profit_abs"], LOSS["profit_abs"]])


def test_journal_rejects_inconsistent_trade():
    bad = {**WIN, "profit_abs": 999.0}
    with pytest.raises(ValueError, match="profit_abs"):
        journal(trades([bad]), RATES)


def test_open_trades_are_not_taxable():
    j = journal(trades([WIN, {**LOSS, "is_open": True, "close_date": None, "close_rate": None}]), RATES)
    assert len(j) == 1


def test_each_leg_uses_its_own_date_rate():
    rates = RateBook({pd.Timestamp("2026-03-01").date(): 1.70, pd.Timestamp("2026-03-10").date(): 1.75})
    r = journal(trades([WIN]), rates).iloc[0]
    assert r["rate_open"] == 1.70 and r["rate_close"] == 1.75
    assert r["pnl_azn"] == pytest.approx(659.34 * 1.75 - 600.60 * 1.70)


def test_tax_year_is_baku_local_date_of_sale():
    # 2026-12-31 22:00 UTC = 2027-01-01 02:00 Bakı → 2027-ci il
    late = {**WIN, "close_date": "2026-12-31 22:00"}
    rates = RateBook({pd.Timestamp("2026-03-01").date(): 1.7, pd.Timestamp("2027-01-01").date(): 1.7})
    assert journal(trades([late]), rates).iloc[0]["tax_year"] == 2027


def test_csv_columns_fixed():
    assert list(journal(trades([WIN]), RATES).columns) == CSV_COLUMNS


# --- məzənnə ----------------------------------------------------------------------

def test_rate_falls_back_to_previous_published_day_and_records_it():
    rb = RateBook({pd.Timestamp("2026-03-06").date(): 1.70})  # cümə
    rate, used = rb.get(pd.Timestamp("2026-03-08").date())    # bazar
    assert rate == 1.70 and str(used) == "2026-03-06"


def test_rate_gap_over_7_days_is_an_error():
    rb = RateBook({pd.Timestamp("2026-03-01").date(): 1.70})
    with pytest.raises(KeyError, match="2026-03-10"):
        rb.get(pd.Timestamp("2026-03-10").date())


CBAR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ValCurs Date="12.10.2026" Name="AZN məzənnələri">
 <ValType Type="Bank metalları"><Valute Code="XAU"><Nominal>1 t.u.</Nominal><Value>5000.0</Value></Valute></ValType>
 <ValType Type="Xarici valyutalar">
  <Valute Code="EUR"><Nominal>1</Nominal><Name>1 Avro</Name><Value>1.9512</Value></Valute>
  <Valute Code="USD"><Nominal>1</Nominal><Name>1 ABŞ dolları</Name><Value>1.7</Value></Valute>
 </ValType>
</ValCurs>"""


def test_parse_cbar_usd():
    assert parse_cbar_usd(CBAR_XML) == 1.7


def test_parse_cbar_without_usd_fails_loudly():
    with pytest.raises(ValueError):
        parse_cbar_usd("<ValCurs></ValCurs>")


# --- illik xülasə -------------------------------------------------------------------

def test_year_summary_by_hand():
    s = year_summary(journal(trades([WIN, LOSS]), RATES))
    row = s.loc[2026]
    win_azn = (0.01 * 66000 * 0.999 - 0.01 * 60000 * 1.001) * 1.70
    loss_azn = (0.01 * 63000 * 0.999 - 0.01 * 66000 * 1.001) * 1.70
    assert row["n_trades"] == 2
    assert row["gains_azn"] == pytest.approx(win_azn)
    assert row["losses_azn"] == pytest.approx(-loss_azn)
    assert row["net_azn"] == pytest.approx(win_azn + loss_azn)
    assert row["tax_azn"] == pytest.approx(max(win_azn + loss_azn, 0) * 0.14)


def test_negative_year_has_no_tax():
    s = year_summary(journal(trades([LOSS]), RATES))
    assert s.loc[2026, "tax_azn"] == 0.0
