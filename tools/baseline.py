"""BASELINE — buy & hold nəticəsi (Phase 0.3).

Strategiyalar bununla müqayisə olunur. Rəqəmlər findings.md-yə bir dəfə yazılır
və dəyişdirilmir.

Fərziyyələr (strategiya backtest-i ilə eyni):
- Giriş: dövrün ilk gündəlik şamının `open` qiyməti, çıxış: son şamın `close`-u
- Komissiya + slippage: hər tərəfə 0.15% (`--fee 0.0015` ilə eyni)
- Vergi: 14% — yalnız müsbət xalis gəlirdən (Vergi Məcəlləsi 99.3.8)
- Drawdown: gündəlik bağlanış qiymətləri üzrə (gün içi dib nəzərə alınmır)
- 50/50 portfel: başlanğıcda bərabər bölünür, rebalans yoxdur

Konteynerdə işlətmə (ai_trader qovluğundan):
    docker compose run --rm --entrypoint python freqtrade /freqtrade/tools/baseline.py
"""

import math
import sys
from pathlib import Path

import pandas as pd

FEE = 0.0015
TAX = 0.14
PERIODS = {
    "IS": ("2023-01-01", "2025-01-01"),
    "OOS": ("2025-01-01", "2026-09-30"),
}
PAIRS = ["BTC_USDT", "ETH_USDT"]
DATA_DIR = Path("/freqtrade/user_data/data/binance")


def _equity(df: pd.DataFrame) -> pd.Series:
    """Girişdə 1.0, sonra hər günün bağlanışı / giriş qiyməti."""
    if df.empty:
        raise ValueError("Dövrdə şam yoxdur")
    entry = df["open"].iloc[0]
    return pd.concat([pd.Series([1.0]), df["close"] / entry], ignore_index=True)


def max_drawdown(equity: pd.Series) -> float:
    """Pikdən dibə ən böyük düşüş (müsbət kəsr, 0.25 = 25%)."""
    peak = equity.cummax()
    return float(((peak - equity) / peak).max())


def annual_volatility(prices: pd.Series) -> float:
    logret = (prices / prices.shift(1)).apply(math.log).dropna()
    std = logret.std()
    return 0.0 if std == 0 or math.isnan(std) else float(std * math.sqrt(365))


def net_return(gross_multiple: float, fee: float, tax: float) -> float:
    after_fees = (1 - fee) * gross_multiple * (1 - fee) - 1
    return after_fees * (1 - tax) if after_fees > 0 else after_fees


def buy_and_hold(df: pd.DataFrame, fee: float, tax: float) -> dict:
    eq = _equity(df)
    return {
        "gross_return": float(eq.iloc[-1] - 1),
        "net_return": net_return(float(eq.iloc[-1]), fee, tax),
        "max_drawdown": max_drawdown(eq),
        "volatility": annual_volatility(eq),
    }


def portfolio_equity(dfs: list[pd.DataFrame], weights: list[float]) -> pd.Series:
    if not math.isclose(sum(weights), 1.0):
        raise ValueError("Çəkilərin cəmi 1 olmalıdır")
    dates = [tuple(d["date"]) for d in dfs]
    if any(d != dates[0] for d in dates):
        raise ValueError("Aktivlərin tarixləri üst-üstə düşmür")
    return sum(w * _equity(d) for w, d in zip(weights, dfs))


def _row(name: str, period: str, eq: pd.Series) -> str:
    gross = float(eq.iloc[-1] - 1)
    net = net_return(float(eq.iloc[-1]), FEE, TAX)
    return (
        f"| {name} | {period} | {gross:+.1%} | {net:+.1%} | {max_drawdown(eq):.1%} "
        f"| {annual_volatility(eq):.1%} |"
    )


def main(data_dir: Path = DATA_DIR) -> int:
    from data_quality import slice_period

    frames = {}
    for pair in PAIRS:
        path = data_dir / f"{pair}-1d.feather"
        if not path.exists():
            print(f"XƏTA: {path} yoxdur")
            return 1
        frames[pair] = pd.read_feather(path)

    print(f"Komissiya: {FEE:.2%} hər tərəfə, vergi: {TAX:.0%} (yalnız gəlirdən)\n")
    print("| Aktiv | Dövr | Brüt gəlir | Xalis gəlir | Maks. drawdown | İllik volatillik |")
    print("|---|---|---|---|---|---|")
    for period, (start, end) in PERIODS.items():
        label = f"{period} [{start}, {end})"
        sliced = {p: slice_period(df, start, end) for p, df in frames.items()}
        for pair, df in sliced.items():
            print(_row(pair.replace("_", "/"), label, _equity(df)))
        print(_row("50/50", label, portfolio_equity(list(sliced.values()), [0.5, 0.5])))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR))
