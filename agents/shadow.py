"""Kölgə portfel — supervayzerin qərarları burada simulyasiya olunur, HEÇ VAXT icra olunmur.

Müqayisə ədalətli olsun deyə TrendEmaAtr paper ilə eyni qaydalar (plan §4):
10 000 USDT, risk 0.5% (risk modulunun position_size-i), stop = giriş − 3×ATR14(4h),
maks. 2 mövqe, komissiya 0.15% hər tərəfdə.
"""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from risk.limits import position_size  # noqa: E402

START_EQUITY = 10_000.0
RISK_PCT = 0.005
FEE = 0.0015
ATR_MULT = 3.0
MAX_OPEN = 2


@dataclass
class Position:
    pair: str
    entry: float
    stop: float
    amount: float
    opened: str  # ISO, UTC


class ShadowBook:
    def __init__(self, equity: float = START_EQUITY, positions: dict | None = None,
                 trades: list | None = None):
        self.equity = equity
        self.positions: dict[str, Position] = positions or {}
        self.trades: list[dict] = trades or []

    def _close(self, pair: str, price: float, when: pd.Timestamp, reason: str) -> None:
        p = self.positions.pop(pair)
        pnl = p.amount * price * (1 - FEE) - p.amount * p.entry * (1 + FEE)
        self.equity += pnl
        self.trades.append({"pair": pair, "opened": p.opened, "closed": when.isoformat(),
                            "entry": p.entry, "exit": price, "amount": p.amount,
                            "pnl": pnl, "reason": reason})

    def check_stops(self, candles: dict[str, pd.DataFrame]) -> list[str]:
        """Girişdən SONRAKI 4h şamlar: açılış stopdan aşağıdırsa — açılışda, yoxsa low ≤ stop → stopda."""
        closed = []
        for pair in list(self.positions):
            p = self.positions[pair]
            df = candles.get(pair)
            if df is None:
                continue
            after = df[df["date"] > pd.Timestamp(p.opened)].sort_values("date")
            for row in after.itertuples():
                if row.open <= p.stop:
                    self._close(pair, float(row.open), row.date, "stop (boşluq)")
                elif row.low <= p.stop:
                    self._close(pair, p.stop, row.date, "stop")
                else:
                    continue
                closed.append(pair)
                break
        return closed

    def apply(self, decisions: dict[str, str], prices: dict[str, float], atrs: dict[str, float],
              now: pd.Timestamp, max_new: int) -> list[tuple[str, str]]:
        """Əvvəl ÇIX-lar (slot boşalsın), sonra AL-lar. Hər qərarın nəticəsi qaytarılır."""
        events = []
        for pair, d in decisions.items():
            if d == "ÇIX":
                if pair in self.positions:
                    self._close(pair, prices[pair], now, "supervayzer")
                    events.append((pair, "bağlandı"))
                else:
                    events.append((pair, "mövqe yoxdur"))
        opened = 0
        for pair, d in decisions.items():
            if d != "AL":
                continue
            if pair in self.positions:
                events.append((pair, "artıq açıqdır"))
            elif len(self.positions) >= MAX_OPEN:  # struktur limit — risk rejimindən asılı deyil
                events.append((pair, "slot yoxdur"))
            elif opened >= max_new:
                events.append((pair, "risk limiti"))
            else:
                entry, stop = prices[pair], prices[pair] - ATR_MULT * atrs[pair]
                if stop <= 0:
                    events.append((pair, "stop hesablanmır"))
                    continue
                stake = position_size(self.equity, entry, stop, RISK_PCT, fee=FEE)
                self.positions[pair] = Position(pair, entry, stop, stake / entry, now.isoformat())
                opened += 1
                events.append((pair, "açıldı"))
        return events

    def mtm_equity(self, prices: dict[str, float]) -> float:
        """Reallaşmış kapital + açıq mövqelərin cari qiymətlə (çıxış komissiyası daxil) nəticəsi."""
        return self.equity + sum(p.amount * prices[p.pair] * (1 - FEE) - p.amount * p.entry * (1 + FEE)
                                 for p in self.positions.values())

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"equity": self.equity, "trades": self.trades,
                "positions": {k: asdict(v) for k, v in self.positions.items()}}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1))

    @classmethod
    def load(cls, path: Path) -> "ShadowBook":
        if not path.exists():
            return cls()
        d = json.loads(path.read_text())
        return cls(d["equity"], {k: Position(**v) for k, v in d["positions"].items()}, d["trades"])
