from collections.abc import Sequence

from src.indicators import ema
from src.models import Candle, Signal, SignalSide


def ema_cross_signal(
    candles: Sequence[Candle],
    fast_period: int,
    slow_period: int,
    take_profit_pct: float,
    stop_loss_pct: float,
) -> Signal:
    if len(candles) < max(fast_period, slow_period) + 2:
        return Signal(SignalSide.FLAT, "not enough candles", candles[-1].close if candles else 0.0)

    closes = [candle.close for candle in candles]
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    previous_fast, current_fast = fast[-2], fast[-1]
    previous_slow, current_slow = slow[-2], slow[-1]
    entry = closes[-1]

    if previous_fast <= previous_slow and current_fast > current_slow:
        return Signal(
            SignalSide.LONG,
            f"EMA{fast_period} crossed above EMA{slow_period}",
            entry,
            stop_loss_price=entry * (1 - stop_loss_pct),
            take_profit_price=entry * (1 + take_profit_pct),
        )

    if previous_fast >= previous_slow and current_fast < current_slow:
        return Signal(
            SignalSide.SHORT,
            f"EMA{fast_period} crossed below EMA{slow_period}",
            entry,
            stop_loss_price=entry * (1 + stop_loss_pct),
            take_profit_price=entry * (1 - take_profit_pct),
        )

    return Signal(SignalSide.FLAT, "no EMA cross", entry)
