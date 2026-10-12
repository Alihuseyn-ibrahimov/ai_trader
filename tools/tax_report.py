"""Vergi jurnalı — kripto gəliri üzrə illik hesabat (Faza 2 dizaynı §4).

Azərbaycan: kripto gəliri sahibkarlıqdan kənar gəlirdir, 14% (Vergi Məcəlləsi 99.3.8),
VÖEN tələb olunur, bəyannamə növbəti ilin 31 martına qədər. Baza: satış − alış qiyməti.

Qaydalar (kodda):
- Yalnız bağlanmış əməliyyatlar (açıq mövqe reallaşmış gəlir deyil).
- Hər ayağı öz tarixinin CBAR USD/AZN məzənnəsi ilə: alış → açılış günü, satış → bağlanış günü.
  USDT ≈ USD fərziyyəsidir (hesabatda yazılır).
- Vergi ili = satışın Bakı vaxtı ilə tarixi.
- Məzənnə yoxdursa (həftəsonu/bayram) son 7 gündə ən yaxın əvvəlki dərc olunmuş məzənnə;
  istifadə olunan tarix CSV-də göstərilir. 7 gündən çox boşluq → xəta (səssiz fərziyyə yox).
- Komissiyalar xərcə daxildir (Freqtrade profit_abs ilə eyni). Zərərin növbəti ilə keçirilməsi
  və komissiyaların çıxılması mühasiblə dəqiqləşdirilməlidir — bu alət məsləhət vermir.

Serverdə:
    docker compose exec -T paper python /freqtrade/tools/tax_report.py --year 2026
"""

import argparse
import datetime as dt
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

CONFIG = Path("/freqtrade/user_data/config.paper.json")
RATES_CACHE = Path("/freqtrade/user_data/cbar_usd_azn.csv")
OUT_DIR = Path("/freqtrade/user_data/tax")
BAKU = "Asia/Baku"
TAX_RATE = 0.14
MAX_RATE_GAP_DAYS = 7
CBAR_URL = "https://www.cbar.az/currencies/{:%d.%m.%Y}.xml"
USER_AGENT = "Mozilla/5.0 (compatible; ai-trader-tax/1.0)"

CSV_COLUMNS = [
    "tax_year", "pair", "open_date", "close_date", "amount", "open_rate", "close_rate",
    "fee_open", "fee_close", "cost_usdt", "proceeds_usdt", "pnl_usdt",
    "rate_open", "rate_open_date", "rate_close", "rate_close_date",
    "cost_azn", "proceeds_azn", "pnl_azn",
]


class RateBook:
    """CBAR USD/AZN məzənnələri (tarix → məzənnə)."""

    def __init__(self, rates: dict[dt.date, float]):
        self.rates = dict(rates)

    def get(self, day: dt.date) -> tuple[float, dt.date]:
        for back in range(MAX_RATE_GAP_DAYS + 1):
            d = day - dt.timedelta(days=back)
            if d in self.rates:
                return self.rates[d], d
        raise KeyError(f"{day} üçün son {MAX_RATE_GAP_DAYS} gündə CBAR USD/AZN məzənnəsi yoxdur")


def parse_cbar_usd(xml_text: str) -> float:
    root = ET.fromstring(xml_text)
    for v in root.iter("Valute"):
        if v.get("Code") == "USD":
            nominal = float((v.findtext("Nominal") or "1").split()[0])
            return float(v.findtext("Value")) / nominal
    raise ValueError("CBAR cavabında USD məzənnəsi yoxdur")


def _local_date(ts: pd.Timestamp) -> dt.date:
    return ts.tz_convert(BAKU).date()


def journal(trades: pd.DataFrame, rates: RateBook) -> pd.DataFrame:
    closed = trades[~trades["is_open"].astype(bool)].sort_values("close_date")
    rows = []
    for t in closed.itertuples():
        cost = t.amount * t.open_rate * (1 + t.fee_open)
        proceeds = t.amount * t.close_rate * (1 - t.fee_close)
        pnl = proceeds - cost
        if abs(pnl - t.profit_abs) > max(0.01, abs(t.profit_abs) * 1e-4):
            raise ValueError(f"{t.pair} {t.close_date}: hesablanan nəticə {pnl:.4f} ≠ "
                             f"Freqtrade profit_abs {t.profit_abs:.4f} — data yoxlanmalıdır")
        r_open, d_open = rates.get(_local_date(t.open_date))
        r_close, d_close = rates.get(_local_date(t.close_date))
        rows.append({
            "tax_year": _local_date(t.close_date).year, "pair": t.pair,
            "open_date": t.open_date, "close_date": t.close_date, "amount": t.amount,
            "open_rate": t.open_rate, "close_rate": t.close_rate,
            "fee_open": t.fee_open, "fee_close": t.fee_close,
            "cost_usdt": cost, "proceeds_usdt": proceeds, "pnl_usdt": pnl,
            "rate_open": r_open, "rate_open_date": d_open,
            "rate_close": r_close, "rate_close_date": d_close,
            "cost_azn": cost * r_open, "proceeds_azn": proceeds * r_close,
            "pnl_azn": proceeds * r_close - cost * r_open,
        })
    return pd.DataFrame(rows, columns=CSV_COLUMNS)


def year_summary(j: pd.DataFrame) -> pd.DataFrame:
    g = j.groupby("tax_year")["pnl_azn"]
    s = pd.DataFrame({
        "n_trades": g.size(),
        "gains_azn": g.apply(lambda x: x[x > 0].sum()),
        "losses_azn": g.apply(lambda x: -x[x < 0].sum()),
        "net_azn": g.sum(),
    })
    s["tax_azn"] = s["net_azn"].clip(lower=0) * TAX_RATE
    return s


# --- şəbəkə və CLI (serverdə) ------------------------------------------------------

def load_rates(cache: Path, days: set[dt.date]) -> RateBook:
    rates: dict[dt.date, float] = {}
    if cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        rates = {d.date(): float(r) for d, r in zip(df["date"], df["usd_azn"])}
    need = set()
    for day in days:
        need.update(day - dt.timedelta(days=b) for b in range(MAX_RATE_GAP_DAYS + 1))
    for day in sorted(need - set(rates)):
        if day > dt.date.today():
            continue
        try:
            req = urllib.request.Request(CBAR_URL.format(day), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (sabit https ünvanı)
                rates[day] = parse_cbar_usd(resp.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001 — həmin gün dərc olunmayıb ola bilər; RateBook yoxlayır
            print(f"CBAR {day}: alınmadı ({type(e).__name__})", file=sys.stderr)
    cache.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(sorted(rates.items()), columns=["date", "usd_azn"]).to_csv(cache, index=False)
    return RateBook(rates)


def main() -> int:
    from freqtrade.data.btanalysis import load_trades_from_db

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    trades = load_trades_from_db(config["db_url"])
    closed = trades[~trades["is_open"].astype(bool)] if not trades.empty else trades
    if closed.empty:
        print("Bağlanmış əməliyyat yoxdur — vergi jurnalı boşdur.")
        return 0
    days = {_local_date(t) for t in pd.concat([closed["open_date"], closed["close_date"]])}
    j = journal(trades, load_rates(RATES_CACHE, days))
    if args.year:
        j = j[j["tax_year"] == args.year]

    if config.get("dry_run", True):
        print("⚠️ PAPER (dry_run) — bu, REAL vergi hesabatı deyil, yalnız alətin sınağıdır.\n")
    print("Fərziyyələr: USDT ≈ USD; CBAR USD/AZN; komissiyalar xərcdə; zərər keçirilmir.")
    print("Bəyannaməyə qədər mühasiblə yoxla.\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for year, part in j.groupby("tax_year"):
        path = OUT_DIR / f"tax_journal_{year}.csv"
        part.to_csv(path, index=False)
        print(f"{year}: {len(part)} əməliyyat → {path}")
    print("\n" + year_summary(j).round(2).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
