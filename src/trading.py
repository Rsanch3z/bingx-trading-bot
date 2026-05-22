from typing import Optional

from src.exchange import BingXClient
from src.journal import TradeJournal
from src.models import OrderResult, PositionPlan, Signal
from src.risk import build_position_plan


def execute_signal(
    client: BingXClient,
    journal: TradeJournal,
    symbol: str,
    signal: Signal,
    equity_usdt: float,
    win_rate: float,
    win_loss_ratio: float,
    max_kelly_fraction: float,
    max_risk_per_trade_pct: float,
    leverage: int,
) -> tuple[Optional[PositionPlan], Optional[OrderResult]]:
    plan = build_position_plan(
        signal=signal,
        equity_usdt=equity_usdt,
        win_rate=win_rate,
        win_loss_ratio=win_loss_ratio,
        max_kelly_fraction=max_kelly_fraction,
        max_risk_per_trade_pct=max_risk_per_trade_pct,
        leverage=leverage,
    )
    if plan is None:
        return None, None

    order = client.place_bracket_order(symbol, plan)
    journal.record_open(plan, order, signal.reason)
    return plan, order
