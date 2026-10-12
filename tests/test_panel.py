"""Gündəlik HTML panel (tools/panel.py) — təmiz render, şəbəkəsiz."""

import re

import pandas as pd
import pytest

from panel import floor_distance, nice_ticks, render_panel, scale_xy, telegram_document

NOW = pd.Timestamp("2026-10-20 05:15", tz="UTC")


def eq(values, start="2026-10-19"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D"), dtype=float)


def data(**kw):
    d = {
        "now": NOW,
        "paper": {"equity": eq([10_000, 10_050, 9_980]), "start": 10_000.0, "floor": 7_000.0,
                  "open": [{"pair": "BTC/USDT", "entry": 84000.0, "current": 85000.0, "pnl": 12.5,
                            "opened": "2026-10-19 08:00"}],
                  "closed": [{"pair": "ETH/USDT", "closed": "2026-10-20 04:00", "pnl": -20.0}],
                  "n_closed": 1},
        "shadow": {"equity": eq([10_000, 10_010], start="2026-10-20"),
                   "open": [], "closed": [], "n_closed": 0,
                   "decisions": [{"time": "2026-10-20T05:10:00+00:00", "pair": "SOL/USDT",
                                  "action": "AL", "confidence": 0.6, "outcome": "açıldı",
                                  "rationale": "<script>alert(1)</script> trend"}],
                   "runs": 8, "failed_runs": 1},
    }
    d.update(kw)
    return d


def test_nice_ticks_are_round_and_cover_range():
    t = nice_ticks(9_980, 10_050, 4)
    assert t[0] <= 9_980 and t[-1] >= 10_050
    assert all(v % 10 == 0 for v in t) and len(t) <= 6


def test_flat_equity_gets_readable_whole_ticks():
    t = nice_ticks(10_000, 10_000, 4)
    assert t[0] < 10_000 < t[-1] and all(float(v).is_integer() for v in t)


def test_scale_xy_maps_extremes_to_box():
    pts = scale_xy([0, 1, 2], [10.0, 20.0, 15.0], x0=0, x1=100, y0=0, y1=50, ymin=10, ymax=20)
    assert pts[0] == (0.0, 50.0) and pts[1] == (50.0, 0.0) and pts[2] == (100.0, 25.0)


def test_floor_distance():
    assert floor_distance(10_000, 7_000) == pytest.approx(30.0)
    assert floor_distance(7_000, 7_000) == 0.0


def test_render_escapes_untrusted_agent_text():
    html = render_panel(data())
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_render_has_both_series_legend_table_and_kpis():
    html = render_panel(data())
    assert html.count("<path") >= 2                 # iki xətt
    assert "TrendEmaAtr (paper)" in html and "Agentlər (kölgə)" in html
    assert "<table" in html and "9 980" in html     # cədvəl görünüşü (dəyər hover-a bağlı deyil)
    assert "1 / 30" in html and "0 / 30" in html
    assert "30.0%" in html or "29.9%" in html       # alt xəttə məsafə (9980 → 29.86%)
    assert "1 / 8" in html                           # uğursuz agent qaçışları


def test_render_handles_empty_shadow_history():
    d = data()
    d["shadow"]["equity"] = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    html = render_panel(d)
    assert "Agentlər (kölgə)" in html and "data yoxdur" in html.lower() or "<path" in html


def test_embedded_json_cannot_break_out_of_script():
    d = data()
    d["paper"]["open"][0]["pair"] = "</script><b>x"
    html = render_panel(d)
    for block in re.findall(r"<script[^>]*>(.*?)</script>", html, flags=re.S):
        assert "</script" not in block.lower()


def test_telegram_document_multipart():
    url, body, ctype = telegram_document("TOKEN", "42", "panel.html", "<html>ə</html>", "Panel")
    assert url == "https://api.telegram.org/botTOKEN/sendDocument"
    boundary = ctype.split("boundary=")[1]
    assert body.count(boundary.encode()) == 4         # 3 hissə + son
    assert b'name="chat_id"' in body and b"42" in body
    assert b'filename="panel.html"' in body and "<html>ə</html>".encode() in body


def test_shadow_fee_matches_shadow_book():
    from pathlib import Path

    if not (Path(__file__).resolve().parent.parent / "agents").exists():
        pytest.skip("agents/ yoxdur (Freqtrade konteyneri)")
    from agents.shadow import FEE
    from panel import SHADOW_FEE

    assert SHADOW_FEE == FEE
