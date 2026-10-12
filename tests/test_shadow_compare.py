"""Kölgə portfel ↔ TrendEmaAtr paper müqayisəsi (agent plan §5) — əl hesabı ilə."""

import pandas as pd
import pytest

from shadow_compare import build_message, compare, side_metrics

D = lambda s: pd.Timestamp(s)  # noqa: E731


def eq(values, start="2026-10-19"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def test_side_metrics_by_hand():
    m = side_metrics([100.0, -50.0, 30.0], eq([10_000, 10_100, 9_595, 10_080]))
    assert m["n"] == 3
    assert m["pf"] == pytest.approx(130 / 50)
    assert m["net"] == pytest.approx(80.0) and m["net_pct"] == pytest.approx(0.8)
    assert m["dd"] == pytest.approx((10_100 - 9_595) / 10_100)


def test_side_metrics_empty():
    m = side_metrics([], eq([10_000]))
    assert m["n"] == 0 and m["pf"] == 0.0 and m["net"] == 0.0 and m["dd"] == 0.0


def good(**kw):
    m = {"n": 31, "pf": 1.6, "net": 500.0, "net_pct": 5.0, "dd": 0.08}
    m.update(kw)
    return m


def test_wait_until_30_trades_or_24_months():
    r = compare(good(n=12), good(), months=3.0)
    assert r["status"] == "GÖZLƏ"
    assert compare(good(n=12), good(pf=1.0), months=24.0)["status"] != "GÖZLƏ"


def test_pass_requires_absolute_criteria_and_beating_paper():
    assert compare(good(), good(pf=1.3, dd=0.10), months=6)["status"] == "KEÇDİ"
    r = compare(good(pf=1.25), good(pf=1.3, dd=0.10), months=6)       # paper-dan pis PF
    assert r["status"] == "KEÇMƏDİ"
    assert [c["ok"] for c in r["checks"]] == [True, True, True, False, True]
    assert compare(good(dd=0.21), good(pf=1.0, dd=0.30), months=6)["status"] == "KEÇMƏDİ"
    assert compare(good(net=-1.0), good(pf=1.0, dd=0.30), months=6)["status"] == "KEÇMƏDİ"


def test_message_is_azerbaijani_and_marks_shadow():
    msg = build_message(good(n=3), good(n=5), compare(good(n=3), good(n=5), 0.5),
                        D("2026-10-19"), D("2026-11-01"))
    assert "KÖLGƏ" in msg and "TrendEmaAtr" in msg and "GÖZLƏ" in msg
    assert "3 / 30" in msg and "2026-10-19" in msg
