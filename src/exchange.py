from collections.abc import Mapping, Sequence
from typing import Any, Optional

import ccxt

from src.models import Candle, OrderResult, PositionPlan, SignalSide


class BingXClient:
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        dry_run: bool = True,
        sandbox: bool = False,
        api_base_url: str = "",
    ) -> None:
        self.dry_run = dry_run
        self.exchange = ccxt.bingx(
            {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {
                    "defaultType": "swap",
                },
            }
        )
        if sandbox:
            self.exchange.set_sandbox_mode(True)
        if api_base_url:
            self._set_api_base_url(api_base_url)

    def _set_api_base_url(self, api_base_url: str) -> None:
        base_url = api_base_url.rstrip("/")
        if not base_url.endswith("/openApi"):
            base_url = f"{base_url}/openApi"
        api_urls = self.exchange.urls.get("api", {})
        if isinstance(api_urls, Mapping):
            self.exchange.urls["api"] = {key: base_url for key in api_urls}
        else:
            self.exchange.urls["api"] = base_url

    def fetch_candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        raw: Sequence[Sequence[Any]] = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        return [
            Candle(
                timestamp_ms=int(item[0]),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
            )
            for item in raw
        ]

    def fetch_equity_usdt(self, fallback: float) -> float:
        if self.dry_run:
            return fallback

        balance = self.exchange.fetch_balance()
        total = balance.get("total", {})
        return float(total.get("USDT") or fallback)

    def fetch_balance(self) -> dict[str, Any]:
        return self.exchange.fetch_balance()

    def fetch_available_balance(self, asset: str) -> float:
        if self.dry_run:
            return 1_000_000
        balance = self.fetch_balance()
        free = balance.get("free", {})
        value = free.get(asset)
        if value is None and asset != "USDT":
            value = free.get("USDT")
        if value is None:
            value = free.get("VST")
        return float(value or 0)

    def fetch_total_balance(self, asset: str) -> float:
        if self.dry_run:
            return 0
        balance = self.fetch_balance()
        total = balance.get("total", {})
        value = total.get(asset)
        if value is None and asset != "USDT":
            value = total.get("USDT")
        if value is None:
            value = total.get("VST")
        return float(value or 0)

    def fetch_open_positions(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return []
        return [dict(item) for item in self.exchange.fetch_positions()]

    def fetch_open_position_symbols(self) -> set[str]:
        symbols: set[str] = set()
        for position in self.fetch_open_positions():
            symbol = str(position.get("symbol") or "")
            contracts = position.get("contracts")
            if contracts is None:
                info = position.get("info", {})
                contracts = info.get("positionAmt") or info.get("positionAmount") or info.get("quantity")
            try:
                size = abs(float(contracts or 0))
            except (TypeError, ValueError):
                size = 0
            if symbol and size > 0:
                symbols.add(symbol)
        return symbols

    def has_open_position(self, symbol: str, side: SignalSide) -> bool:
        expected_side = "long" if side == SignalSide.LONG else "short"
        for position in self.fetch_open_positions():
            if str(position.get("symbol") or "") != symbol:
                continue
            position_side = str(position.get("side") or "").lower()
            info = position.get("info", {})
            raw_position_side = str(info.get("positionSide") or "").lower()
            if position_side and position_side != expected_side:
                continue
            if raw_position_side and raw_position_side != expected_side:
                continue
            contracts = position.get("contracts")
            if contracts is None:
                contracts = info.get("positionAmt") or info.get("positionAmount") or info.get("quantity")
            try:
                if abs(float(contracts or 0)) > 0:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def cancel_order_safe(self, order_id: str, symbol: str) -> Optional[str]:
        if not order_id or order_id == "dry-run":
            return None
        if self.dry_run:
            return "dry-run"
        try:
            self.exchange.cancel_order(order_id, symbol)
            return order_id
        except Exception as exc:
            print(f"warning: failed to cancel order_id={order_id} symbol={symbol}: {exc}")
            return None

    def cancel_position_protection_orders(self, position: Any) -> list[str]:
        canceled: list[str] = []
        for order_id in (
            getattr(position, "stop_loss_order_id", ""),
            getattr(position, "take_profit_1_order_id", ""),
            getattr(position, "take_profit_2_order_id", ""),
        ):
            canceled_order_id = self.cancel_order_safe(order_id, getattr(position, "symbol"))
            if canceled_order_id:
                canceled.append(canceled_order_id)
        return canceled

    def fetch_ticker_last(self, symbol: str) -> float:
        ticker = self.exchange.fetch_ticker(symbol)
        price = ticker.get("last") or ticker.get("close")
        if price is None:
            raise ValueError(f"ticker last price is unavailable for {symbol}")
        return float(price)

    def calculate_quantity_from_notional(self, symbol: str, notional_usdt: float) -> tuple[float, float]:
        self.exchange.load_markets()
        last_price = self.fetch_ticker_last(symbol)
        if last_price <= 0:
            raise ValueError(f"invalid last price for {symbol}: {last_price}")
        quantity = float(self.exchange.amount_to_precision(symbol, notional_usdt / last_price))
        if quantity <= 0:
            raise ValueError(f"calculated quantity is zero for {symbol}; notional may be too small")
        return quantity, last_price

    def place_market_order_by_notional(
        self,
        symbol: str,
        side: SignalSide,
        notional_usdt: float,
        leverage: int,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
    ) -> OrderResult:
        quantity, last_price = self.calculate_quantity_from_notional(symbol, notional_usdt)

        if self.dry_run:
            return OrderResult(
                order_id="dry-run",
                status="simulated",
                message=(
                    f"Simulated market {side.value} {quantity:.8f} {symbol} "
                    f"notional={notional_usdt:.2f} ref_price={last_price:.8f}"
                ),
            )

        order_side = "buy" if side == SignalSide.LONG else "sell"
        position_side = "LONG" if side == SignalSide.LONG else "SHORT"
        params: dict[str, Any] = {"hedged": True}
        if stop_loss_price is not None:
            params["stopLoss"] = {"triggerPrice": stop_loss_price}
        if take_profit_price is not None:
            params["takeProfit"] = {"triggerPrice": take_profit_price}

        try:
            self.exchange.set_leverage(leverage, symbol, params={"side": position_side})
        except Exception as exc:
            print(f"warning: failed to set leverage={leverage} side={position_side} for {symbol}: {exc}")

        order = self.exchange.create_market_order(symbol, order_side, quantity, params=params)
        return OrderResult(
            order_id=str(order.get("id", "")),
            status=str(order.get("status", "submitted")),
            message=str(order),
        )

    def close_position_market(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        if quantity <= 0:
            raise ValueError("close quantity must be positive")

        if self.dry_run:
            return OrderResult(
                order_id="dry-run",
                status="simulated",
                message=f"Simulated close {quantity:.8f} {symbol} for {side.value}",
            )

        close_side = "sell" if side == SignalSide.LONG else "buy"
        position_side = "LONG" if side == SignalSide.LONG else "SHORT"
        amount = float(self.exchange.amount_to_precision(symbol, quantity))
        order = self.exchange.create_market_order(
            symbol,
            close_side,
            amount,
            params={"reduceOnly": True, "hedged": True, "positionSide": position_side},
        )
        return OrderResult(
            order_id=str(order.get("id", "")),
            status=str(order.get("status", "submitted")),
            message=str(order),
        )

    def place_reduce_only_trigger_market_order(
        self,
        symbol: str,
        side: SignalSide,
        quantity: float,
        trigger_price: float,
        trigger_kind: str,
    ) -> OrderResult:
        if quantity <= 0:
            raise ValueError("trigger order quantity must be positive")
        if trigger_kind not in {"stop_loss", "take_profit"}:
            raise ValueError("trigger_kind must be stop_loss or take_profit")

        if self.dry_run:
            return OrderResult(
                order_id="dry-run",
                status="simulated",
                message=(
                    f"Simulated {trigger_kind} reduce-only {quantity:.8f} {symbol} "
                    f"trigger={trigger_price:.8f}"
                ),
            )

        close_side = "sell" if side == SignalSide.LONG else "buy"
        self.exchange.load_markets()
        amount = float(self.exchange.amount_to_precision(symbol, quantity))
        params: dict[str, Any] = {"reduceOnly": True, "hedged": True}
        order_type = "STOP_MARKET"
        if trigger_kind == "stop_loss":
            params["stopLossPrice"] = trigger_price
        else:
            order_type = "TAKE_PROFIT_MARKET"
            params["takeProfitPrice"] = trigger_price

        order = self.exchange.create_order(symbol, order_type, close_side, amount, None, params=params)
        return OrderResult(
            order_id=str(order.get("id", "")),
            status=str(order.get("status", "submitted")),
            message=str(order),
        )

    def place_bracket_order(self, symbol: str, plan: PositionPlan) -> OrderResult:
        if self.dry_run:
            return OrderResult(
                order_id="dry-run",
                status="simulated",
                message=f"Simulated {plan.side.value} {plan.quantity:.8f} {symbol}",
            )

        side = "buy" if plan.side == SignalSide.LONG else "sell"
        params = {
            "leverage": plan.leverage,
            "stopLoss": {"triggerPrice": plan.stop_loss_price},
            "takeProfit": {"triggerPrice": plan.take_profit_price},
        }
        order = self.exchange.create_market_order(symbol, side, plan.quantity, params=params)
        return OrderResult(
            order_id=str(order.get("id", "")),
            status=str(order.get("status", "submitted")),
            message=str(order),
        )
