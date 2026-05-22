from src.config import load_settings
from src.exchange import BingXClient
from src.journal import TradeJournal
from src.signals import ema_cross_signal
from src.trading import execute_signal


def run_once() -> None:
    settings = load_settings()
    client = BingXClient(settings.api_key, settings.api_secret, dry_run=settings.dry_run)
    journal = TradeJournal(settings.trade_journal_path)

    candles = client.fetch_candles(settings.symbol, settings.timeframe, settings.candle_limit)
    signal = ema_cross_signal(
        candles=candles,
        fast_period=settings.fast_ema,
        slow_period=settings.slow_ema,
        take_profit_pct=settings.take_profit_pct,
        stop_loss_pct=settings.stop_loss_pct,
    )

    equity = client.fetch_equity_usdt(settings.starting_equity_usdt)
    stats = journal.stats()
    win_rate = stats.win_rate if stats.total >= 20 else settings.estimated_win_rate

    plan, order = execute_signal(
        client=client,
        journal=journal,
        symbol=settings.symbol,
        signal=signal,
        equity_usdt=equity,
        win_rate=win_rate,
        win_loss_ratio=settings.estimated_win_loss_ratio,
        max_kelly_fraction=settings.max_kelly_fraction,
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        leverage=settings.leverage,
    )

    print(f"symbol={settings.symbol} price={signal.entry_price:.4f} signal={signal.side.value} reason={signal.reason}")
    print(f"dry_run={settings.dry_run} equity_usdt={equity:.2f} historical_win_rate={stats.win_rate:.2%}")

    if plan is None:
        print("No order planned.")
        return

    print(
        "planned_order "
        f"side={plan.side.value} qty={plan.quantity:.8f} "
        f"notional={plan.notional_usdt:.2f} risk={plan.risk_usdt:.4f} "
        f"sl={plan.stop_loss_price:.4f} tp={plan.take_profit_price:.4f}"
    )
    print(f"order_status={order.status} order_id={order.order_id} message={order.message}")


if __name__ == "__main__":
    run_once()
