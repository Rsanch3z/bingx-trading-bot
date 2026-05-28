import hashlib
import hmac
import logging
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from .config import Config

BINGX_BASE_URL = "https://open-api.bingx.com"
logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    symbol: str
    action: str        # BUY | SELL | CLOSE
    side: str          # LONG | SHORT
    order_type: str    # MARKET
    size_pct: float
    tp_pct: float
    sl_pct: float
    close_position: bool
    strategy: str
    timestamp: str


class BingXExecutor:
    def __init__(self, config: Config):
        self.config = config

    def _sign(self, params: dict) -> str:
        query = urlencode(sorted(params.items()))
        return hmac.new(
            self.config.bingx_api_secret.encode(),
            query.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method: str, path: str, params: dict) -> dict:
        params["timestamp"] = str(int(time.time() * 1000))
        params["signature"] = self._sign(params)
        url = f"{BINGX_BASE_URL}{path}"
        headers = {"X-BX-APIKEY": self.config.bingx_api_key}
        resp = requests.request(method, url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code", 0) != 0:
            raise ValueError(f"BingX API error: {data}")
        return data

    def get_balance(self) -> float:
        data = self._request("GET", "/openApi/swap/v2/user/balance", {})
        return float(data["data"]["balance"]["balance"])

    def get_open_positions(self) -> list:
        data = self._request("GET", "/openApi/swap/v2/trade/openPositions", {})
        return data.get("data", {}).get("positions", [])

    def place_order(self, signal: TradeSignal, balance: float) -> dict:
        if self.config.dry_run:
            logger.info(
                "DRY RUN: %s %s %.2f%% of %.2f USDT",
                signal.action, signal.symbol, signal.size_pct, balance,
            )
            return {"dry_run": True, "signal": signal.__dict__}

        size_usdt = round(balance * (signal.size_pct / 100), 4)
        bingx_symbol = signal.symbol.replace("-", "")

        params = {
            "symbol": bingx_symbol,
            "side": signal.action,           # BUY | SELL
            "positionSide": signal.side,     # LONG | SHORT
            "type": "MARKET",
            "quantity": str(size_usdt),
        }

        if signal.tp_pct > 0:
            params["takeProfit"] = str(signal.tp_pct)
        if signal.sl_pct > 0:
            params["stopLoss"] = str(signal.sl_pct)

        result = self._request("POST", "/openApi/swap/v2/trade/order", params)
        logger.info("Order placed: %s", result)
        return result

    def close_position(self, symbol: str) -> dict:
        if self.config.dry_run:
            logger.info("DRY RUN: close %s", symbol)
            return {"dry_run": True}

        bingx_symbol = symbol.replace("-", "")
        positions = self.get_open_positions()

        for pos in positions:
            if pos["symbol"] == bingx_symbol:
                close_side = "SELL" if pos["positionSide"] == "LONG" else "BUY"
                params = {
                    "symbol": bingx_symbol,
                    "side": close_side,
                    "positionSide": pos["positionSide"],
                    "type": "MARKET",
                    "quantity": str(pos["positionAmt"]),
                }
                result = self._request("POST", "/openApi/swap/v2/trade/order", params)
                logger.info("Position closed: %s", result)
                return result

        return {"error": "no_open_position", "symbol": symbol}
