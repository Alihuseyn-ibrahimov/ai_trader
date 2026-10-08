"""AI Trader risk modulu — saf Python, Freqtrade-dən asılı deyil.

Strategiya nə təklif edirsə etsin, giriş bu moduldan keçir. Faza 2-3-də canlı
botun vetosu da eyni koddur. Limitləri yalnız insan, konfiqurasiya ilə dəyişir.
"""

from risk.limits import (
    RiskConfig,
    TradeDecision,
    check_entry,
    daily_loss_breached,
    floor_breached,
    position_size,
)

__all__ = [
    "RiskConfig",
    "TradeDecision",
    "check_entry",
    "daily_loss_breached",
    "floor_breached",
    "position_size",
]
