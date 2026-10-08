import math
from dataclasses import dataclass, fields

# Sərt tavanlar: konfiqurasiya səhv yazılsa belə bunlardan yuxarı qalxmaq olmaz.
MAX_RISK_PER_TRADE = 0.05
MAX_DAILY_LOSS_LIMIT = 0.10


@dataclass(frozen=True)
class RiskConfig:
    risk_per_trade: float = 0.01   # hər əməliyyatda kapitalın maks. itki payı
    daily_loss_limit: float = 0.03  # gün ərzində bu qədər itki → həmin gün giriş yoxdur
    floor_ratio: float = 0.7       # alt xətt: başlanğıc kapitalın bu payı (0.7 = maks. 30% itki)
    max_open_trades: int = 2

    def __post_init__(self):
        if not 0 < self.risk_per_trade <= MAX_RISK_PER_TRADE:
            raise ValueError(f"risk_per_trade (0, {MAX_RISK_PER_TRADE}] aralığında olmalıdır")
        if not 0 < self.daily_loss_limit <= MAX_DAILY_LOSS_LIMIT:
            raise ValueError(f"daily_loss_limit (0, {MAX_DAILY_LOSS_LIMIT}] aralığında olmalıdır")
        if not 0 <= self.floor_ratio < 1:
            raise ValueError("floor_ratio [0, 1) aralığında olmalıdır")
        if not isinstance(self.max_open_trades, int) or self.max_open_trades < 1:
            raise ValueError("max_open_trades müsbət tam ədəd olmalıdır")

    @classmethod
    def from_dict(cls, data: dict) -> "RiskConfig":
        """Naməlum açar xətadır: yazı səhvi limitin səssizcə default qalmasına səbəb olmasın."""
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Naməlum risk parametrləri: {sorted(unknown)}")
        return cls(**data)


@dataclass(frozen=True)
class TradeDecision:
    allowed: bool
    reason: str


def position_size(
    equity: float,
    entry: float,
    stop: float,
    risk_pct: float,
    fee: float = 0.0,
    floor: float | None = None,
) -> float:
    """Stake məbləği (quote valyutada, məs. USDT) — yalnız long, leverage-siz.

    Stop-loss işə düşsə, komissiyalar daxil itki `equity * risk_pct`-dən çox
    olmur və kapitalı `floor`-dan aşağı salmır.
    """
    if equity <= 0:
        raise ValueError("equity müsbət olmalıdır")
    if entry <= 0 or stop <= 0:
        raise ValueError("entry və stop müsbət olmalıdır")
    if stop >= entry:
        raise ValueError("long mövqedə stop girişdən aşağı olmalıdır")

    max_loss = equity * risk_pct
    if floor is not None:
        if equity <= floor:
            return 0.0
        max_loss = min(max_loss, equity - floor)

    loss_per_unit = (entry - stop) + entry * fee + stop * fee
    stake = max_loss / loss_per_unit * entry
    return min(stake, equity)


def _reached(value: float, threshold: float) -> bool:
    return value >= threshold or math.isclose(value, threshold, rel_tol=1e-9)


def daily_loss_breached(day_start_equity: float, equity: float, limit: float) -> bool:
    if day_start_equity <= 0:
        raise ValueError("day_start_equity müsbət olmalıdır")
    loss = (day_start_equity - equity) / day_start_equity
    return _reached(loss, limit)


def floor_breached(equity: float, floor: float) -> bool:
    return equity <= floor or math.isclose(equity, floor, rel_tol=1e-9)


def check_entry(
    config: RiskConfig,
    equity: float,
    start_equity: float,
    day_start_equity: float,
    open_trades: int,
) -> TradeDecision:
    """Yeni girişə veto. Ardıcıllıq: alt xətt → gündəlik itki → açıq mövqe sayı."""
    if floor_breached(equity, start_equity * config.floor_ratio):
        return TradeDecision(False, "floor")
    if daily_loss_breached(day_start_equity, equity, config.daily_loss_limit):
        return TradeDecision(False, "daily_loss")
    if open_trades >= config.max_open_trades:
        return TradeDecision(False, "max_open_trades")
    return TradeDecision(True, "ok")
