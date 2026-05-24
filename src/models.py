from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class PositionStatus(str, Enum):
    OPEN = "open"
    TP1_HIT = "tp1_hit"
    CLOSED_BY_TP2 = "closed_by_tp2"
    CLOSED_BY_SL = "closed_by_sl"
    MANUALLY_CLOSED = "manually_closed"
    STALE_MISSING_ON_EXCHANGE = "stale_missing_on_exchange"


@dataclass(frozen=True)
class Candle:
    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    side: SignalSide
    reason: str
    entry_price: float
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None


@dataclass(frozen=True)
class PositionPlan:
    side: SignalSide
    entry_price: float
    quantity: float
    notional_usdt: float
    risk_usdt: float
    stop_loss_price: float
    take_profit_price: float
    leverage: int


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: str
    message: str


@dataclass(frozen=True)
class ManagedPosition:
    signal_id: str
    symbol: str
    side: SignalSide
    entry_price: float
    quantity: float
    remaining_quantity: float
    notional_usdt: float
    margin_usdt: float
    leverage: int
    stop_loss_price: float
    current_stop_loss_price: float
    take_profit_1_price: float
    take_profit_2_price: float
    tp1_closed: bool
    closed: bool
    entry_order_id: str
    stop_loss_order_id: str = ""
    take_profit_1_order_id: str = ""
    take_profit_2_order_id: str = ""
    status: PositionStatus = PositionStatus.OPEN
    closed_reason: str = ""
    closed_at: str = ""
