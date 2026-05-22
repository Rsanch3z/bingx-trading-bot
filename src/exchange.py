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
