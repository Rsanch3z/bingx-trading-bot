from dataclasses import dataclass
from enum import Enum
from typing import Optional


class SignalSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


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
