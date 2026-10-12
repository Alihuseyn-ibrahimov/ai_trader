"""Agentlərə verilən faktlar — hamısı KODLA hesablanır (LLM rəqəm uydurmur)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "tools"))
sys.path.insert(0, str(_ROOT))

from market_brief import pair_facts  # noqa: E402
from signals.indicators import atr, rsi  # noqa: E402


def technical_facts(d1: pd.DataFrame, h4: pd.DataFrame) -> dict:
    """market_brief faktları + 4h RSI14, ATR14 (mütləq və qiymətin %-i)."""
    f = pair_facts(d1, h4)
    a = float(atr(h4.reset_index(drop=True), 14).iloc[-1])
    price = float(h4["close"].iloc[-1])
    f["rsi14"] = round(float(rsi(h4["close"].astype(float).reset_index(drop=True), 14).iloc[-1]), 1)
    f["atr14"] = round(a, 6 if a < 1 else 4)
    f["atr_pct"] = round(a / price * 100, 2)
    return f


def risk_facts(d1: dict[str, pd.DataFrame]) -> dict:
    """Bazar səviyyəsində: 30 günlük orta cüt korrelyasiyası və BTC-nin 30 günlük zirvədən düşüşü."""
    rets = pd.DataFrame({p: np.log(df["close"].astype(float).reset_index(drop=True)).diff()
                         for p, df in d1.items()}).iloc[-30:]
    corr = rets.corr().to_numpy()
    upper = corr[np.triu_indices_from(corr, k=1)]
    btc = d1["BTC/USDT"]["close"].astype(float).iloc[-30:]
    return {
        "avg_corr_30d": round(float(np.nanmean(upper)), 2),
        "btc_dd_30d": round(float((btc.max() - btc.iloc[-1]) / btc.max() * 100), 2),
    }
