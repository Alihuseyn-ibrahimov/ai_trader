"""RiskManagedStrategy — bütün AI Trader strategiyalarının baza sinfi.

Strategiya yalnız "nə vaxt al / sat" qərarını verir. Mövqe ölçüsü, giriş vetosu
və alt xətt (kill switch) burada, `risk` modulu ilə idarə olunur.

Qayda: bütün callback-lar **fail closed** işləyir. Freqtrade callback xətasında
default-a qayıdır (stake → bütün balans, confirm → True). Ona görə xətanı burada
tuturuq və girişi bloklayırıq.

Alt sinif nümunəsi (eyni qovluqda):
    import sys; from pathlib import Path
    sys.path.append(str(Path(__file__).parent))
    from risk_managed import RiskManagedStrategy
"""

import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute

# ai_trader/ kökü: lokal repo-da ai_trader/, konteynerdə /freqtrade (risk/ ora qoşulub)
_AI_ROOT = Path(__file__).resolve().parents[2]
if str(_AI_ROOT) not in sys.path:
    sys.path.insert(0, str(_AI_ROOT))

from risk import RiskConfig, check_entry, floor_breached, position_size  # noqa: E402
from signals.tags import parse_stop_dist  # noqa: E402

logger = logging.getLogger(__name__)

# Backtest `--fee 0.0015` ilə eyni: 0.1% komissiya + 0.05% slippage, hər tərəfə
ASSUMED_FEE = 0.0015


class RiskManagedStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short = False  # spot: short yoxdur
    # True: ATR stopu ən yüksək qiymətin arxasınca gedir (chandelier). Yalnız
    # enter_tag-da stop məsafəsi olan əməliyyatlara aid; use_custom_stoploss lazımdır.
    atr_trailing = False

    def bot_start(self, **kwargs) -> None:
        self.risk_config = RiskConfig.from_dict(self.config.get("ai_risk", {}))
        self.risk_vetoes: Counter = Counter()
        self._day = None
        self._day_start_equity = None

    @property
    def protections(self):
        # Risk modulunu tamamlayır: ardıcıl stop-loss-lardan və drawdown-dan sonra fasilə.
        # Backtest-də yalnız `--enable-protections` ilə işləyir.
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": 2},
            {
                "method": "StoplossGuard",
                "lookback_period_candles": 24,
                "trade_limit": 3,
                "stop_duration_candles": 12,
                "only_per_pair": False,
            },
            {
                "method": "MaxDrawdown",
                "lookback_period_candles": 48,
                "trade_limit": 5,
                "stop_duration_candles": 24,
                "max_allowed_drawdown": 0.15,
            },
        ]

    # --- köməkçilər (testlərdə əvəzlənə bilər) ---

    def _equity(self) -> float:
        """Reallaşmış kapital: başlanğıc + bağlanmış əməliyyatların nəticəsi."""
        return float(self.wallets.get_total_stake_amount())

    def _start_equity(self) -> float:
        return float(self.wallets.get_starting_balance())

    def _floor(self) -> float:
        return self._start_equity() * self.risk_config.floor_ratio

    def _open_trade_count(self) -> int:
        return Trade.get_open_trade_count()

    def stop_price(self, pair: str, rate: float, entry_tag: str | None = None) -> float:
        """Girişdə planlaşdırılan stop. Tag-da stop məsafəsi varsa (ATR) — o,
        yoxdursa sabit `stoploss`. `custom_stoploss` və audit eyni mənbəni oxuyur."""
        dist = parse_stop_dist(entry_tag)
        if dist is not None:
            return rate - dist
        return rate * (1 + self.stoploss)

    # --- Freqtrade callback-ları ---

    def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
        day = current_time.date()
        if day != self._day:
            self._day = day
            self._day_start_equity = self._equity()

    def custom_stake_amount(self, pair, current_time, current_rate, proposed_stake,
                            min_stake, max_stake, leverage, entry_tag, side, **kwargs) -> float:
        try:
            stake = position_size(
                equity=self._equity(),
                entry=current_rate,
                stop=self.stop_price(pair, current_rate, entry_tag),
                risk_pct=self.risk_config.risk_per_trade,
                fee=ASSUMED_FEE,
                floor=self._floor(),
            )
            return min(stake, max_stake)
        except Exception:
            logger.exception("custom_stake_amount xətası — giriş bloklandı (%s)", pair)
            return 0.0

    def confirm_trade_entry(self, pair, order_type, amount, rate, time_in_force,
                            current_time, entry_tag, side, **kwargs) -> bool:
        try:
            decision = check_entry(
                config=self.risk_config,
                equity=self._equity(),
                start_equity=self._start_equity(),
                day_start_equity=self._day_start_equity or self._equity(),
                open_trades=self._open_trade_count(),
            )
        except Exception:
            logger.exception("confirm_trade_entry xətası — giriş bloklandı (%s)", pair)
            self.risk_vetoes["error"] += 1
            return False
        if not decision.allowed:
            self.risk_vetoes[decision.reason] += 1
            logger.info("Risk vetosu: %s %s (%s)", pair, current_time, decision.reason)
        return decision.allowed

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit,
                        after_fill, **kwargs):
        """ATR stopu (tag-dan). Tag yoxdursa None → sabit `stoploss` qalır."""
        dist = parse_stop_dist(trade.enter_tag)
        if dist is None:
            return None
        stop_abs = trade.open_rate - dist
        if self.atr_trailing:
            stop_abs = max(stop_abs, trade.max_rate - dist)
        return stoploss_from_absolute(stop_abs, current_rate, is_short=False, leverage=1.0)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        """Kill switch: reallaşmış kapital + bu mövqenin cari zərəri alt xəttə çatsa — çıx."""
        try:
            projected = self._equity() + trade.stake_amount * current_profit
            if floor_breached(projected, self._floor()):
                logger.warning("ALT XƏTT: %s bağlanır (proqnoz kapital %.2f)", pair, projected)
                return "floor_kill_switch"
        except Exception:
            logger.exception("custom_exit xətası — ehtiyat üçün mövqe bağlanır (%s)", pair)
            return "risk_error_exit"
        return None
