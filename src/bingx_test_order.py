import os

from src.config import load_settings
from src.exchange import BingXClient
from src.models import SignalSide


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


def _side_from_env() -> SignalSide:
    value = os.getenv("TEST_ORDER_SIDE", "long").strip().lower()
    if value in {"long", "buy"}:
        return SignalSide.LONG
    if value in {"short", "sell"}:
        return SignalSide.SHORT
    raise ValueError("TEST_ORDER_SIDE must be long/buy or short/sell")


def run() -> None:
    settings = load_settings()
    confirm = os.getenv("CONFIRM_BINGX_ORDER", "").strip().lower()
    if settings.dry_run:
        raise ValueError("DRY_RUN must be false before placing a BingX test order")
    if confirm != "yes":
        raise ValueError("set CONFIRM_BINGX_ORDER=yes to place a real BingX test order")

    side = _side_from_env()
    client = BingXClient(
        settings.api_key,
        settings.api_secret,
        dry_run=False,
        sandbox=settings.bingx_sandbox,
        api_base_url=settings.bingx_api_base_url,
    )
    _, reference_price = client.calculate_quantity_from_notional(
        settings.test_order_symbol,
        settings.test_order_notional_usdt,
    )
    tp_pct = _float_env("TEST_ORDER_TP_PCT", 0.0)
    sl_pct = _float_env("TEST_ORDER_SL_PCT", 0.0)
    take_profit = None
    stop_loss = None
    if side == SignalSide.LONG:
        if tp_pct > 0:
            take_profit = reference_price * (1 + tp_pct)
        if sl_pct > 0:
            stop_loss = reference_price * (1 - sl_pct)
    else:
        if tp_pct > 0:
            take_profit = reference_price * (1 - tp_pct)
        if sl_pct > 0:
            stop_loss = reference_price * (1 + sl_pct)

    print(
        "placing_test_order "
        f"symbol={settings.test_order_symbol} side={side.value} "
        f"notional={settings.test_order_notional_usdt:.2f} leverage={settings.leverage} "
        f"reference_price={reference_price:.8f} tp={take_profit} sl={stop_loss}"
    )
    order = client.place_market_order_by_notional(
        symbol=settings.test_order_symbol,
        side=side,
        notional_usdt=settings.test_order_notional_usdt,
        leverage=settings.leverage,
        stop_loss_price=stop_loss,
        take_profit_price=take_profit,
    )
    print(f"order_status={order.status} order_id={order.order_id}")
    print(order.message)


if __name__ == "__main__":
    run()
