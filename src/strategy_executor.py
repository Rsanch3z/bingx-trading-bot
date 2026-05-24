from dataclasses import replace
from datetime import datetime, timezone
import re
from typing import Any, Optional

from src.alerts import TradingAlert
from src.config import Settings
from src.exchange import BingXClient
from src.models import ManagedPosition, PositionStatus, SignalSide
from src.position_store import ActivePositionStore


TP1_CLOSE_FRACTION = 0.60


def execute_alert_entry(
    alert: TradingAlert,
    settings: Settings,
    client: BingXClient,
    store: ActivePositionStore,
) -> dict[str, Any]:
    signal_age = _signal_age_seconds(alert.signal_id)
    if signal_age is not None and signal_age > settings.max_signal_age_seconds:
        return {
            "ok": True,
            "opened": False,
            "reason": "signal expired",
            "signal_age_seconds": signal_age,
            "max_signal_age_seconds": settings.max_signal_age_seconds,
        }

    if alert.win_rate < settings.min_win_rate:
        return {
            "ok": True,
            "opened": False,
            "reason": "win_rate below minimum",
            "win_rate": alert.win_rate,
            "min_win_rate": settings.min_win_rate,
        }

    sync_results = sync_positions_with_exchange(client, store)
    if sync_results:
        print(f"position_sync results={sync_results}")

    total_balance = client.fetch_total_balance(settings.account_balance_asset)
    if total_balance >= settings.target_wallet_balance_usdt:
        return {
            "ok": True,
            "opened": False,
            "graduated": True,
            "reason": "target wallet balance reached; switch to advanced strategy",
            "wallet_balance": total_balance,
        }

    available_balance = client.fetch_available_balance(settings.account_balance_asset)
    if available_balance < settings.trade_margin_usdt:
        return {
            "ok": True,
            "opened": False,
            "reason": "insufficient available balance",
            "available_balance": available_balance,
            "required_margin": settings.trade_margin_usdt,
        }

    if alert.take_profit_2 is None:
        return {"ok": True, "opened": False, "reason": "tp2 is required for staged exits"}

    open_symbols = client.fetch_open_position_symbols()
    if alert.symbol in open_symbols:
        return {"ok": True, "opened": False, "reason": "symbol already has an active position", "symbol": alert.symbol}
    if len(open_symbols) >= settings.max_total_positions:
        return {
            "ok": True,
            "opened": False,
            "reason": "max total positions reached",
            "active_position_count": len(open_symbols),
        }

    local_active_symbols = {position.symbol for position in store.load() if not position.closed}
    if alert.symbol in local_active_symbols:
        return {"ok": True, "opened": False, "reason": "symbol already tracked locally", "symbol": alert.symbol}

    notional = settings.trade_margin_usdt * settings.leverage
    quantity, reference_price = client.calculate_quantity_from_notional(alert.symbol, notional)
    order = client.place_market_order_by_notional(
        symbol=alert.symbol,
        side=alert.side,
        notional_usdt=notional,
        leverage=settings.leverage,
    )
    position = ManagedPosition(
        signal_id=alert.signal_id,
        symbol=alert.symbol,
        side=alert.side,
        entry_price=reference_price,
        quantity=quantity,
        remaining_quantity=quantity,
        notional_usdt=notional,
        margin_usdt=settings.trade_margin_usdt,
        leverage=settings.leverage,
        stop_loss_price=alert.stop_loss,
        current_stop_loss_price=alert.stop_loss,
        take_profit_1_price=alert.take_profit,
        take_profit_2_price=alert.take_profit_2,
        tp1_closed=False,
        closed=False,
        entry_order_id=order.order_id,
    )
    position, protection_results = ensure_exchange_protection(position, client)
    store.upsert(position)
    return {
        "ok": True,
        "opened": True,
        "dry_run": settings.dry_run,
        "signal_id": alert.signal_id,
        "symbol": alert.symbol,
        "side": alert.side.value,
        "order_id": order.order_id,
        "order_status": order.status,
        "quantity": quantity,
        "notional_usdt": notional,
        "margin_usdt": settings.trade_margin_usdt,
        "leverage": settings.leverage,
        "tp1": alert.take_profit,
        "tp2": alert.take_profit_2,
        "sl": alert.stop_loss,
        "protection_orders": protection_results,
    }


def monitor_active_positions_once(
    settings: Settings,
    client: BingXClient,
    store: ActivePositionStore,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    results.extend(sync_positions_with_exchange(client, store))
    updated: list[ManagedPosition] = []

    for position in store.load():
        if position.closed:
            updated.append(position)
            continue

        price = client.fetch_ticker_last(position.symbol)
        next_position = position

        if _stop_loss_hit(position, price):
            order = client.close_position_market(position.symbol, position.side, position.remaining_quantity)
            client.cancel_position_protection_orders(position)
            next_position = _close_position(position, "closed_by_sl")
            results.append(_result(position, "stop_loss", price, order.order_id, position.remaining_quantity))
            updated.append(next_position)
            continue

        if not position.tp1_closed and _tp1_hit(position, price):
            close_quantity = position.quantity * TP1_CLOSE_FRACTION
            order = client.close_position_market(position.symbol, position.side, close_quantity)
            remaining = max(position.remaining_quantity - close_quantity, 0)
            next_position = replace(
                position,
                remaining_quantity=remaining,
                current_stop_loss_price=position.take_profit_1_price,
                tp1_closed=True,
                status=PositionStatus.TP1_HIT,
            )
            results.append(_result(position, "tp1_close_60pct_move_sl", price, order.order_id, close_quantity))

        if next_position.tp1_closed and not next_position.closed and _tp2_hit(next_position, price):
            close_quantity = next_position.remaining_quantity
            order = client.close_position_market(next_position.symbol, next_position.side, close_quantity)
            client.cancel_position_protection_orders(next_position)
            results.append(_result(next_position, "tp2_close_remaining", price, order.order_id, close_quantity))
            next_position = _close_position(next_position, "closed_by_tp2")

        updated.append(next_position)

    store.save(updated)
    return results


def sync_positions_with_exchange(
    client: BingXClient,
    store: ActivePositionStore,
) -> list[dict[str, Any]]:
    positions = store.load()
    results: list[dict[str, Any]] = []
    updated: list[ManagedPosition] = []
    changed = False

    for position in positions:
        if position.closed:
            updated.append(position)
            continue
        if client.has_open_position(position.symbol, position.side):
            updated.append(position)
            continue

        canceled = client.cancel_position_protection_orders(position)
        updated.append(_close_position(position, "manually_closed"))
        changed = True
        results.append(
            {
                "signal_id": position.signal_id,
                "symbol": position.symbol,
                "side": position.side.value,
                "action": "position_missing_on_exchange",
                "status": "manually_closed",
                "canceled_order_ids": canceled,
            }
        )

    if changed:
        store.save(updated)
    return results


def ensure_exchange_protection(
    position: ManagedPosition,
    client: BingXClient,
) -> tuple[ManagedPosition, dict[str, str]]:
    updates: dict[str, str] = {}
    next_position = position

    if not _has_exchange_order_id(position.stop_loss_order_id):
        order = client.place_reduce_only_trigger_market_order(
            symbol=position.symbol,
            side=position.side,
            quantity=position.remaining_quantity,
            trigger_price=position.current_stop_loss_price,
            trigger_kind="stop_loss",
        )
        updates["stop_loss_order_id"] = order.order_id
        next_position = replace(next_position, stop_loss_order_id=order.order_id)

    if not _has_exchange_order_id(position.take_profit_1_order_id):
        order = client.place_reduce_only_trigger_market_order(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity * TP1_CLOSE_FRACTION,
            trigger_price=position.take_profit_1_price,
            trigger_kind="take_profit",
        )
        updates["take_profit_1_order_id"] = order.order_id
        next_position = replace(next_position, take_profit_1_order_id=order.order_id)

    if not _has_exchange_order_id(position.take_profit_2_order_id):
        order = client.place_reduce_only_trigger_market_order(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity * (1 - TP1_CLOSE_FRACTION),
            trigger_price=position.take_profit_2_price,
            trigger_kind="take_profit",
        )
        updates["take_profit_2_order_id"] = order.order_id
        next_position = replace(next_position, take_profit_2_order_id=order.order_id)

    return next_position, updates


def _has_exchange_order_id(order_id: str) -> bool:
    return bool(order_id and order_id != "dry-run")


def _close_position(position: ManagedPosition, reason: str) -> ManagedPosition:
    status = PositionStatus.MANUALLY_CLOSED
    if reason == "closed_by_sl":
        status = PositionStatus.CLOSED_BY_SL
    elif reason == "closed_by_tp2":
        status = PositionStatus.CLOSED_BY_TP2
    elif reason == "stale_missing_on_exchange":
        status = PositionStatus.STALE_MISSING_ON_EXCHANGE
    return replace(
        position,
        remaining_quantity=0,
        closed=True,
        status=status,
        closed_reason=reason,
        closed_at=datetime.now(timezone.utc).isoformat(),
    )


def _signal_age_seconds(signal_id: str) -> Optional[float]:
    match = re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})?", signal_id)
    if not match:
        return None
    try:
        value = match.group(0)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        signal_time = datetime.fromisoformat(value)
        if signal_time.tzinfo is None:
            signal_time = signal_time.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - signal_time.astimezone(timezone.utc)).total_seconds()
    except ValueError:
        return None
    return None


def _tp1_hit(position: ManagedPosition, price: float) -> bool:
    if position.side == SignalSide.LONG:
        return price >= position.take_profit_1_price
    return price <= position.take_profit_1_price


def _tp2_hit(position: ManagedPosition, price: float) -> bool:
    if position.side == SignalSide.LONG:
        return price >= position.take_profit_2_price
    return price <= position.take_profit_2_price


def _stop_loss_hit(position: ManagedPosition, price: float) -> bool:
    if position.side == SignalSide.LONG:
        return price <= position.current_stop_loss_price
    return price >= position.current_stop_loss_price


def _result(
    position: ManagedPosition,
    action: str,
    price: float,
    order_id: str,
    quantity: float,
) -> dict[str, Any]:
    return {
        "signal_id": position.signal_id,
        "symbol": position.symbol,
        "side": position.side.value,
        "action": action,
        "price": price,
        "quantity": quantity,
        "order_id": order_id,
    }
