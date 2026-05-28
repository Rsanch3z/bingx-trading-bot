import logging
from dataclasses import dataclass, field
from datetime import date

from .bingx_executor import TradeSignal
from .config import Config

logger = logging.getLogger(__name__)


@dataclass
class RiskState:
    daily_realized_loss_pct: float = 0.0
    open_position_count: int = 0
    circuit_breaker_active: bool = False
    last_reset_date: date = field(default_factory=date.today)


class RiskManager:
    def __init__(self, config: Config):
        self.config = config
        self.state = RiskState()

    def _reset_daily_if_needed(self):
        today = date.today()
        if self.state.last_reset_date != today:
            self.state.daily_realized_loss_pct = 0.0
            self.state.circuit_breaker_active = False
            self.state.last_reset_date = today
            logger.info("Daily risk counters reset")

    def update_daily_loss(self, loss_pct: float):
        self._reset_daily_if_needed()
        self.state.daily_realized_loss_pct += loss_pct
        if self.state.daily_realized_loss_pct >= self.config.max_daily_loss_pct:
            self.state.circuit_breaker_active = True
            logger.warning(
                "Circuit breaker triggered: daily loss %.2f%% >= %.2f%%",
                self.state.daily_realized_loss_pct,
                self.config.max_daily_loss_pct,
            )

    def update_position_count(self, count: int):
        self.state.open_position_count = count

    def evaluate(self, signal: TradeSignal) -> tuple[bool, str]:
        self._reset_daily_if_needed()

        if signal.close_position:
            return True, "close_position bypasses risk checks"

        if self.state.circuit_breaker_active:
            return False, (
                f"circuit breaker active: daily loss "
                f"{self.state.daily_realized_loss_pct:.2f}% >= "
                f"{self.config.max_daily_loss_pct}%"
            )

        if self.state.open_position_count >= self.config.max_open_positions:
            return False, (
                f"max open positions reached: "
                f"{self.state.open_position_count}/{self.config.max_open_positions}"
            )

        if signal.size_pct > self.config.max_single_trade_pct:
            logger.warning(
                "size_pct %.2f clamped to %.2f",
                signal.size_pct, self.config.max_single_trade_pct,
            )
            signal.size_pct = self.config.max_single_trade_pct

        return True, "ok"
