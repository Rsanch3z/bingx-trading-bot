from typing import Optional

from src.models import PositionPlan, Signal, SignalSide
from src.sizing import size_from_kelly


def build_position_plan(
    signal: Signal,
    equity_usdt: float,
    win_rate: float,
    win_loss_ratio: float,
    max_kelly_fraction: float,
    max_risk_per_trade_pct: float,
    leverage: int,
) -> Optional[PositionPlan]:
    if signal.side == SignalSide.FLAT:
        return None
    if signal.stop_loss_price is None or signal.take_profit_price is None:
        raise ValueError("signal must include stop loss and take profit")

    quantity, notional, risk = size_from_kelly(
        signal=signal,
        equity_usdt=equity_usdt,
        win_rate=win_rate,
        win_loss_ratio=win_loss_ratio,
        max_kelly_fraction=max_kelly_fraction,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
        leverage=leverage,
    )
    if quantity <= 0:
        return None

    return PositionPlan(
        side=signal.side,
        entry_price=signal.entry_price,
        quantity=quantity,
        notional_usdt=notional,
        risk_usdt=risk,
        stop_loss_price=signal.stop_loss_price,
        take_profit_price=signal.take_profit_price,
        leverage=leverage,
    )
