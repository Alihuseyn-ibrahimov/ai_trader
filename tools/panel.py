"""Gündəlik HTML panel → Telegram (fayl kimi). Paper bot + agentlərin kölgə portfeli bir yerdə.

Tək, özü-özünə kifayət edən HTML: xarici skript/şrift yoxdur, qrafik inline SVG.
İnternetə heç nə açılmır — fayl Telegram-a göndərilir, telefonda/kompüterdə açılır.
Ticarətə TOXUNMUR: DB və CSV-lər yalnız oxunur; yazılan yeganə fayl user_data/panel.html.

Serverdə (cron 09:15 Bakı, agentlərdən sonra):
    docker compose exec -T paper python /freqtrade/tools/panel.py --send
"""

import argparse
import html
import json
import math
import os
import sys
import urllib.request
import uuid
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

USER_DATA = Path("/freqtrade/user_data")
BAKU = "Asia/Baku"
MIN_TRADES = 30
SHADOW_FEE = 0.0015  # agents/shadow.py FEE ilə eyni (agents/ paper konteynerində yoxdur; testlə bağlı)
SERIES = (("paper", "TrendEmaAtr (paper)"), ("shadow", "Agentlər (kölgə)"))

# Chart box (SVG koordinatları)
# Telefon üçün ölçülüb (fayl əsasən Telegram-da açılır); masaüstündə max-width ilə məhdud.
W, H = 400, 240
PAD_L, PAD_R, PAD_T, PAD_B = 48, 84, 12, 24
SHORT = {"paper": "Paper", "shadow": "Kölgə"}
LABEL_GAP = 14  # uc etiketləri bundan yaxındırsa göstərilmir (legend + tooltip kifayətdir)


# --- təmiz köməkçilər ------------------------------------------------------------

def nice_ticks(lo: float, hi: float, target: int = 4) -> list[float]:
    """1/2/5×10^k addımı ilə yuvarlaq tick-lər, [lo, hi]-ni örtür."""
    mid = (lo + hi) / 2
    if hi - lo < abs(mid) * 0.004 or hi <= lo:  # düz kapital (ilk günlər) → ±0.2% minimum diapazon
        lo, hi = mid - max(abs(mid) * 0.002, 0.5), mid + max(abs(mid) * 0.002, 0.5)
    raw = (hi - lo) / target
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 5, 10) if m * mag >= raw)
    ticks = [math.floor(lo / step) * step]
    while ticks[-1] < hi:  # son tick hi-ni örtməlidir, yoxsa xətt qutudan çıxar
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def scale_xy(xs, ys, x0, x1, y0, y1, ymin, ymax) -> list[tuple[float, float]]:
    xmin, xmax = min(xs), max(xs)
    def sx(x):
        return (x0 + x1) / 2 if xmax == xmin else x0 + (x - xmin) / (xmax - xmin) * (x1 - x0)
    def sy(y):
        return y1 - (y - ymin) / (ymax - ymin) * (y1 - y0)
    return [(round(sx(x), 2), round(sy(y), 2)) for x, y in zip(xs, ys)]


def floor_distance(equity: float, floor: float) -> float:
    """Alt xəttə qədər məsafə, kapitalın %-i ilə."""
    return max(0.0, (equity - floor) / equity * 100) if equity else 0.0


def _num(x: float, d: int = 0) -> str:
    return f"{x:,.{d}f}".replace(",", " ")


def _signed(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "") + _num(abs(x), 2)


def _e(x) -> str:
    return html.escape(str(x), quote=True)


# --- render ----------------------------------------------------------------------

def _chart(paper: pd.Series, shadow: pd.Series) -> tuple[str, dict]:
    dates = sorted(set(paper.index) | set(shadow.index))
    if not dates:
        return '<p class="muted">Kapital tarixçəsi üçün hələ data yoxdur.</p>', {}
    vals = [v for s in (paper, shadow) for v in s.values]
    ticks = nice_ticks(min(vals), max(vals))
    ymin, ymax = ticks[0], ticks[-1]
    day0 = dates[0]
    x_of = {d: (d - day0).days for d in dates}
    x0, x1, y0, y1 = PAD_L, W - PAD_R, PAD_T, H - PAD_B
    all_x = [x_of[d] for d in dates]
    px = [p[0] for p in scale_xy(all_x, [ymin] * len(all_x), x0, x1, y0, y1, ymin, ymax)]

    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" tabindex="0" id="eqchart" '
             f'aria-label="Kapital: paper və kölgə portfel, gündəlik">']
    for t in ticks:
        y = scale_xy([0], [t], 0, 0, y0, y1, ymin, ymax)[0][1]
        parts.append(f'<line class="grid" x1="{x0}" x2="{x1}" y1="{y}" y2="{y}"/>'
                     f'<text class="tick" x="{x0 - 8}" y="{y + 4}" text-anchor="end">{_num(t)}</text>')
    for d, x in ((dates[0], px[0]), (dates[-1], px[-1])):
        parts.append(f'<text class="tick" x="{x}" y="{H - 8}" text-anchor="middle">{d:%d.%m}</text>')

    ends = []
    for i, (key, _label) in enumerate(SERIES, start=1):
        s = paper if key == "paper" else shadow
        if s.empty:
            continue
        pts = scale_xy([x_of[d] for d in s.index], list(s.values), x0, x1, y0, y1, ymin, ymax)
        if len(set(all_x)) == 1:
            pts = [(px[0], y) for _, y in pts]
        path = "M" + " L".join(f"{x},{y}" for x, y in pts)
        lx, ly = pts[-1]
        parts.append(f'<path class="line s{i}" d="{path}"/>'
                     f'<circle class="dot s{i}" cx="{lx}" cy="{ly}" r="4"/>')
        ends.append((lx, ly, f"{SHORT[key]} {_num(s.iloc[-1])}"))
    if len(ends) < 2 or abs(ends[0][1] - ends[1][1]) >= LABEL_GAP:
        parts += [f'<text class="endlabel" x="{lx + 8}" y="{ly + 4}">{_e(t)}</text>' for lx, ly, t in ends]
    parts.append(f'<line id="xhair" class="xhair" x1="0" x2="0" y1="{y0}" y2="{y1}" visibility="hidden"/>')
    parts.append("</svg>")

    js = {"x": px, "d": [f"{d:%Y-%m-%d}" for d in dates],
          "p": [float(paper[d]) if d in paper.index else None for d in dates],
          "s": [float(shadow[d]) if d in shadow.index else None for d in dates]}
    return "".join(parts), js


def _table(head: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f'<p class="muted">{_e(empty)}</p>'
    th = "".join(f"<th>{_e(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def _pnl_cell(x) -> str:
    if x is None:
        return '<span class="muted">—</span>'
    cls = "up" if x > 0 else "down" if x < 0 else ""
    return f'<span class="{cls}">{_signed(x)}</span>'


def _positions(rows: list[dict]) -> list[list[str]]:
    return [[_e(r["pair"]), _num(r["entry"], 4 if r["entry"] < 100 else 2),
             "—" if r.get("current") is None else _num(r["current"], 4 if r["current"] < 100 else 2),
             _pnl_cell(r.get("pnl")), _e(r["opened"])] for r in rows]


def _closed(rows: list[dict]) -> list[list[str]]:
    return [[_e(r["pair"]), _e(r["closed"]), _pnl_cell(r["pnl"])] for r in rows]


def _tile(label: str, value: str, sub: str = "") -> str:
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    return f'<div class="tile"><div class="label">{_e(label)}</div><div class="value">{value}</div>{sub_html}</div>'


def render_panel(d: dict) -> str:
    p, s, now = d["paper"], d["shadow"], d["now"]
    p_eq = float(p["equity"].iloc[-1]) if not p["equity"].empty else p["start"]
    s_eq = float(s["equity"].iloc[-1]) if not s["equity"].empty else None
    chart, js = _chart(p["equity"], s["equity"])

    dates = sorted(set(p["equity"].index) | set(s["equity"].index), reverse=True)
    eq_rows = [[f"{x:%Y-%m-%d}",
                _num(p["equity"][x], 2) if x in p["equity"].index else "—",
                _num(s["equity"][x], 2) if x in s["equity"].index else "—"] for x in dates]

    dec_rows = [[_e(pd.Timestamp(r["time"]).tz_convert(BAKU).strftime("%m-%d %H:%M")), _e(r["pair"]),
                 f'<b>{_e(r["action"])}</b>',
                 "—" if r.get("confidence") in (None, "") or pd.isna(r.get("confidence"))
                 else f'{float(r["confidence"]):.2f}',
                 _e(r.get("outcome") or ""), f'<span class="small">{_e(r.get("rationale") or "")}</span>']
                for r in s["decisions"]]

    tiles = "".join([
        _tile("Paper kapital (USDT)", _num(p_eq, 2), f"başlanğıc {_num(p['start'])}"),
        _tile("Alt xəttə qədər", f"{floor_distance(p_eq, p['floor']):.1f}%",
              f"alt xətt {_num(p['floor'])} USDT"),
        _tile("Paper əməliyyatları", f"{p['n_closed']} / {MIN_TRADES}", "qiymətləndirmə ≥ 30-da"),
        _tile("Kölgə kapital (USDT)", "—" if s_eq is None else _num(s_eq, 2), "icra olunmur"),
        _tile("Kölgə əməliyyatları", f"{s['n_closed']} / {MIN_TRADES}", "plan §5"),
        _tile("Uğursuz agent qaçışları", f"{s['failed_runs']} / {s['runs']}", "ən azı bir agent uğursuz"),
    ])
    legend = "".join(f'<span class="key"><span class="lk s{i}"></span>{_e(label)}</span>'
                     for i, (_, label) in enumerate(SERIES, start=1))
    data_json = json.dumps(js).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    return f"""<!doctype html>
<html lang="az"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Trader paneli</title>
<style>
:root {{ color-scheme: light; --bg:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e;
  --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#eb6834; --up:#006300; --down:#d03b3b; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --bg:#0d0d0d; --surface:#1a1a19;
  --ink:#f0efec; --ink2:#c3c2b7; --muted:#898781; --grid:#2c2c2a; --axis:#383835;
  --ring:rgba(255,255,255,.10); --s1:#3987e5; --s2:#d95926; --up:#0ca30c; --down:#e66767; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:16px; }}
h1 {{ font-size:20px; margin:4px 0 2px; }} h2 {{ font-size:16px; margin:24px 0 8px; }}
.muted {{ color:var(--muted); }} .small {{ font-size:13px; color:var(--ink2); }}
.banner {{ border:1px solid var(--ring); background:var(--surface); border-radius:8px; padding:8px 12px;
  color:var(--ink2); font-size:13px; margin:8px 0 16px; }}
.tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:8px; }}
.tile {{ background:var(--surface); border:1px solid var(--ring); border-radius:8px; padding:10px 12px; }}
.tile .label {{ font-size:13px; color:var(--ink2); }}
.tile .value {{ font-size:22px; font-weight:600; margin-top:2px; }}
.tile .sub {{ font-size:12px; color:var(--muted); }}
.card {{ background:var(--surface); border:1px solid var(--ring); border-radius:8px; padding:12px; position:relative; }}
.legend {{ display:flex; gap:16px; flex-wrap:wrap; font-size:13px; color:var(--ink2); margin-bottom:6px; }}
.key {{ display:inline-flex; align-items:center; gap:6px; }}
.lk {{ display:inline-block; width:16px; height:2px; border-radius:1px; }}
.lk.s1 {{ background:var(--s1); }} .lk.s2 {{ background:var(--s2); }}
svg {{ width:100%; max-width:640px; height:auto; display:block; overflow:visible; }}
.grid {{ stroke:var(--grid); stroke-width:1; }} .xhair {{ stroke:var(--axis); stroke-width:1; }}
.tick {{ fill:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }}
.line {{ fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }}
.line.s1 {{ stroke:var(--s1); }} .line.s2 {{ stroke:var(--s2); }}
.dot {{ stroke:var(--surface); stroke-width:2; }} .dot.s1 {{ fill:var(--s1); }} .dot.s2 {{ fill:var(--s2); }}
.endlabel {{ fill:var(--ink2); font-size:12px; }}
#tip {{ position:absolute; pointer-events:none; background:var(--surface); border:1px solid var(--ring);
  border-radius:6px; padding:6px 8px; font-size:12px; display:none; box-shadow:0 2px 8px rgba(0,0,0,.12); }}
#tip .row {{ display:flex; align-items:center; gap:6px; }} #tip b {{ font-variant-numeric:tabular-nums; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; background:var(--surface);
  border:1px solid var(--ring); border-radius:8px; overflow:hidden; }}
th,td {{ text-align:left; padding:6px 8px; border-bottom:1px solid var(--grid); vertical-align:top; white-space:nowrap; }}
td .small {{ white-space:normal; display:inline-block; min-width:200px; }}
th {{ color:var(--ink2); font-weight:600; }} td {{ font-variant-numeric:tabular-nums; }}
.up {{ color:var(--up); }} .down {{ color:var(--down); }}
.scroll {{ overflow-x:auto; }}
details summary {{ cursor:pointer; color:var(--ink2); font-size:13px; margin-top:8px; }}
</style></head>
<body><main>
<h1>AI Trader paneli</h1>
<div class="muted">{now.tz_convert(BAKU):%Y-%m-%d %H:%M} Bakı · virtual pul, real ticarət yoxdur</div>
<div class="banner">🕶 Kölgə portfel agentlərin qərarlarını yalnız simulyasiya edir — icra olunmur və paper bot-a təsir etmir.</div>
<div class="tiles">{tiles}</div>

<h2>Kapital (gündəlik, açıq mövqelər daxil)</h2>
<div class="card">
<div class="legend">{legend}</div>
{chart}
<div id="tip" role="status"></div>
<details><summary>Cədvəl görünüşü</summary><div class="scroll">
{_table(["Tarix", SERIES[0][1], SERIES[1][1]], eq_rows, "Data yoxdur")}
</div></details>
</div>

<h2>Paper — açıq mövqelər</h2>
<div class="scroll">{_table(["Cüt", "Giriş", "Cari", "Nəticə (USDT)", "Açılıb"], _positions(p["open"]), "Açıq mövqe yoxdur")}</div>
<h2>Paper — son bağlanmış əməliyyatlar</h2>
<div class="scroll">{_table(["Cüt", "Bağlanıb", "Nəticə (USDT)"], _closed(p["closed"]), "Hələ bağlanmış əməliyyat yoxdur")}</div>

<h2>Kölgə — açıq mövqelər</h2>
<div class="scroll">{_table(["Cüt", "Giriş", "Cari", "Nəticə (USDT)", "Açılıb"], _positions(s["open"]), "Açıq kölgə mövqe yoxdur")}</div>
<h2>Kölgə — son bağlanmış əməliyyatlar</h2>
<div class="scroll">{_table(["Cüt", "Bağlanıb", "Nəticə (USDT)"], _closed(s["closed"]), "Hələ bağlanmış kölgə əməliyyatı yoxdur")}</div>
<h2>Agentlərin son qərarları</h2>
<div class="scroll">{_table(["Vaxt", "Cüt", "Qərar", "İnam", "Nəticə", "Əsaslandırma"], dec_rows, "Hələ qərar yoxdur")}</div>
<p class="small">Mənbə: Freqtrade DB, paper_equity.csv, shadow/ (book.json, equity.csv, decisions.csv, runs.jsonl).</p>
</main>
<script>
(function () {{
  var D = {data_json};
  var svg = document.getElementById("eqchart"), tip = document.getElementById("tip");
  if (!svg || !D.x || !D.x.length) return;
  var xh = document.getElementById("xhair"), idx = D.x.length - 1;
  var names = ["TrendEmaAtr (paper)", "Agentlər (kölgə)"], keys = ["p", "s"], cls = ["s1", "s2"];
  function fmt(v) {{  // 10 148.51 — paneldəki Python formatı ilə eyni
    var t = Math.abs(v).toFixed(2).split("."), a = t[0], o = "";
    while (a.length > 3) {{ o = " " + a.slice(-3) + o; a = a.slice(0, -3); }}
    return (v < 0 ? "−" : "") + a + o + "." + t[1];
  }}
  function show(i) {{
    idx = i; var x = D.x[i];
    xh.setAttribute("x1", x); xh.setAttribute("x2", x); xh.setAttribute("visibility", "visible");
    tip.textContent = "";
    var h = document.createElement("div"); h.className = "muted"; h.textContent = D.d[i]; tip.appendChild(h);
    for (var k = 0; k < 2; k++) {{
      var v = D[keys[k]][i]; if (v === null) continue;
      var row = document.createElement("div"); row.className = "row";
      var key = document.createElement("span"); key.className = "lk " + cls[k];
      var b = document.createElement("b"); b.textContent = fmt(v);
      var n = document.createElement("span"); n.className = "muted"; n.textContent = names[k];
      row.appendChild(key); row.appendChild(b); row.appendChild(n); tip.appendChild(row);
    }}
    // SVG-nin offsetLeft/Top-u yoxdur — kartın içində mövqeni rect-lərdən hesabla
    tip.style.display = "block";  // əvvəl göstər: display:none elementin offsetParent-i null-dur
    var r = svg.getBoundingClientRect(), c = tip.offsetParent.getBoundingClientRect(), scale = r.width / {W};
    var px = r.left - c.left + x * scale, left = px + 12;
    if (left + tip.offsetWidth > c.width - 4) left = px - tip.offsetWidth - 12;
    tip.style.left = Math.max(4, left) + "px"; tip.style.top = (r.top - c.top + 8) + "px";
  }}
  function nearest(evt) {{
    var r = svg.getBoundingClientRect(), x = (evt.clientX - r.left) * {W} / r.width, best = 0;
    for (var i = 1; i < D.x.length; i++) if (Math.abs(D.x[i] - x) < Math.abs(D.x[best] - x)) best = i;
    return best;
  }}
  svg.addEventListener("pointermove", function (e) {{ show(nearest(e)); }});
  svg.addEventListener("pointerdown", function (e) {{ show(nearest(e)); }});
  svg.addEventListener("pointerleave", function () {{ tip.style.display = "none"; xh.setAttribute("visibility", "hidden"); }});
  svg.addEventListener("focus", function () {{ show(idx); }});
  svg.addEventListener("blur", function () {{ tip.style.display = "none"; xh.setAttribute("visibility", "hidden"); }});
  svg.addEventListener("keydown", function (e) {{
    if (e.key === "ArrowLeft" && idx > 0) show(idx - 1);
    if (e.key === "ArrowRight" && idx < D.x.length - 1) show(idx + 1);
  }});
}})();
</script>
</body></html>
"""


# --- Telegram (fayl) -------------------------------------------------------------

def telegram_document(token: str, chat_id: str, filename: str, content: str,
                      caption: str) -> tuple[str, bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in (("chat_id", chat_id), ("caption", caption)):
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{filename}"\r\n'
                 f"Content-Type: text/html; charset=utf-8\r\n\r\n".encode() + content.encode() + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return (f"https://api.telegram.org/bot{token}/sendDocument", body,
            f"multipart/form-data; boundary={boundary}")


def send_document(filename: str, content: str, caption: str) -> None:
    token = os.environ.get("FREQTRADE__TELEGRAM__TOKEN", "")
    chat_id = os.environ.get("FREQTRADE__TELEGRAM__CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("FREQTRADE__TELEGRAM__TOKEN / CHAT_ID mühit dəyişənləri yoxdur")
    url, body, ctype = telegram_document(token, chat_id, filename, content, caption)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (sabit https ünvanı)
        if resp.status != 200:
            raise RuntimeError(f"Telegram cavabı: HTTP {resp.status}")


# --- mənbələr (serverdə, paper konteynerində) --------------------------------------

def _load_equity(path: Path) -> pd.Series:
    from shadow_compare import load_equity

    return load_equity(path)


def _baku(ts) -> str:
    return pd.Timestamp(ts).tz_convert(BAKU).strftime("%Y-%m-%d %H:%M")


def collect(ud: Path, prices_fn) -> dict:
    """Bütün mənbələri oxu. prices_fn(pairs) → {pair: qiymət}; xəta olsa qiymətsiz davam."""
    from freqtrade.data.btanalysis import load_trades_from_db

    config = json.loads((ud / "config.paper.json").read_text())
    start = float(config.get("available_capital") or config["dry_run_wallet"])
    trades = load_trades_from_db(config["db_url"])
    is_open = trades["is_open"].astype(bool) if not trades.empty else pd.Series(dtype=bool)
    open_t, closed_t = (trades[is_open], trades[~is_open]) if not trades.empty else (trades, trades)

    sdir = ud / "shadow"
    book = json.loads((sdir / "book.json").read_text()) if (sdir / "book.json").exists() \
        else {"positions": {}, "trades": []}

    pairs = sorted(set(open_t["pair"]) if not open_t.empty else set()) + sorted(book["positions"])
    try:
        prices = prices_fn(sorted(set(pairs))) if pairs else {}
    except Exception as e:  # noqa: BLE001 — qiymət alınmasa panel yenə qurulur, "—" göstərilir
        print(f"XƏBƏRDARLIQ: qiymətlər alınmadı: {e}", file=sys.stderr)
        prices = {}

    paper_open = []
    for r in open_t.itertuples() if not open_t.empty else []:
        cur = prices.get(r.pair)
        pnl = None if cur is None else r.amount * cur * (1 - r.fee_close) - r.stake_amount * (1 + r.fee_open)
        paper_open.append({"pair": r.pair, "entry": float(r.open_rate), "current": cur, "pnl": pnl,
                           "opened": _baku(r.open_date)})
    paper_closed = [] if closed_t.empty else [
        {"pair": r.pair, "closed": _baku(r.close_date), "pnl": float(r.profit_abs)}
        for r in closed_t.sort_values("close_date", ascending=False).head(10).itertuples()]

    shadow_open = []
    for p in book["positions"].values():
        cur = prices.get(p["pair"])
        pnl = None if cur is None else p["amount"] * cur * (1 - SHADOW_FEE) - p["amount"] * p["entry"] * (1 + SHADOW_FEE)
        shadow_open.append({"pair": p["pair"], "entry": p["entry"], "current": cur, "pnl": pnl,
                            "opened": _baku(p["opened"])})
    shadow_closed = [{"pair": t["pair"], "closed": _baku(t["closed"]), "pnl": t["pnl"]}
                     for t in sorted(book["trades"], key=lambda t: t["closed"], reverse=True)[:10]]

    decisions = []
    if (sdir / "decisions.csv").exists():
        df = pd.read_csv(sdir / "decisions.csv", keep_default_na=False)
        decisions = df.tail(14).iloc[::-1].to_dict("records")
    runs = failed = 0
    if (sdir / "runs.jsonl").exists():
        for line in (sdir / "runs.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            runs += 1
            failed += (not r["decision"]["ok"]) or any(not x.get("ok") for x in r["reports"].values())

    return {"now": pd.Timestamp.now(tz="UTC"),
            "paper": {"equity": _load_equity(ud / "paper_equity.csv"), "start": start,
                      "floor": start * float(config["ai_risk"]["floor_ratio"]),
                      "open": paper_open, "closed": paper_closed, "n_closed": len(closed_t)},
            "shadow": {"equity": _load_equity(sdir / "equity.csv"), "open": shadow_open,
                       "closed": shadow_closed, "n_closed": len(book["trades"]),
                       "decisions": decisions, "runs": runs, "failed_runs": failed}}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-data", type=Path, default=USER_DATA)
    parser.add_argument("--send", action="store_true", help="Telegram-a fayl kimi göndər")
    args = parser.parse_args()

    from paper_report import fetch_prices

    config = json.loads((args.user_data / "config.paper.json").read_text())
    data = collect(args.user_data, lambda pairs: fetch_prices(config, pairs))
    page = render_panel(data)
    out = args.user_data / "panel.html"
    out.write_text(page, encoding="utf-8")
    print(f"Panel yazıldı: {out} ({len(page)} bayt)")
    if args.send:
        day = data["now"].tz_convert(BAKU)
        send_document(f"panel_{day:%Y-%m-%d}.html", page, f"📊 AI Trader paneli — {day:%Y-%m-%d}")
        print("Telegram: göndərildi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
