from src.models import Signal, SignalSide


def kelly_fraction(win_rate: float, win_loss_ratio: float) -> float:
    if win_loss_ratio <= 0:
        return 0.0
    loss_rate = 1 - win_rate
    fraction = win_rate - (loss_rate / win_loss_ratio)
    return max(0.0, fraction)


def size_from_kelly(
    signal: Signal,
    equity_usdt: float,
    win_rate: float,
    win_loss_ratio: float,
    max_kelly_fraction: float,
    max_risk_per_trade_pct: float,
    leverage: int,
) -> tuple[float, float, float]:
    if signal.side == SignalSide.FLAT:
        return 0.0, 0.0, 0.0
    if signal.stop_loss_price is None:
        raise ValueError("stop_loss_price is required for position sizing")

    raw_fraction = kelly_fraction(win_rate, win_loss_ratio)
    capped_fraction = min(raw_fraction, max_kelly_fraction, max_risk_per_trade_pct)
    risk_usdt = equity_usdt * capped_fraction

    price_risk = abs(signal.entry_price - signal.stop_loss_price)
    if price_risk <= 0:
        raise ValueError("stop loss must be different from entry price")

    quantity = risk_usdt / price_risk
    notional_usdt = quantity * signal.entry_price
    max_notional = equity_usdt * max(leverage, 1)
    if notional_usdt > max_notional:
        quantity = max_notional / signal.entry_price
        notional_usdt = max_notional
        risk_usdt = quantity * price_risk

    return quantity, notional_usdt, risk_usdt
