from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from src.config import load_settings
from src.models import Signal, SignalSide


QUOTE_ASSETS = ("USDT", "USDC", "USD", "BTC", "ETH")


@dataclass(frozen=True)
class TradingAlert:
    signal_id: str
    symbol: str
    side: SignalSide
    entry: float
    take_profit: float
    stop_loss: float
    win_rate: float
    win_loss_ratio: float
    reason: str

    def to_signal(self) -> Signal:
        return Signal(
            side=self.side,
            reason=self.reason,
            entry_price=self.entry,
            stop_loss_price=self.stop_loss,
            take_profit_price=self.take_profit,
        )

    def to_event(self, source_ip: str = "") -> dict[str, Any]:
        data = asdict(self)
        data["side"] = self.side.value
        data["tp"] = data.pop("take_profit")
        data["sl"] = data.pop("stop_loss")
        data["rr"] = data.pop("win_loss_ratio")
        data["source_ip"] = source_ip
        data["received_at"] = datetime.now(timezone.utc).isoformat()
        return data


def _as_float(payload: dict[str, Any], key: str) -> float:
    value = payload.get(key)
    if value in (None, ""):
        raise ValueError(f"missing {key}")
    return float(value)


def parse_side(raw: Any) -> SignalSide:
    if isinstance(raw, (int, float)):
        if raw > 0:
            return SignalSide.LONG
        if raw < 0:
            return SignalSide.SHORT

    value = str(raw).strip().lower()
    if value in {"1", "1.0"}:
        return SignalSide.LONG
    if value in {"-1", "-1.0"}:
        return SignalSide.SHORT
    if value in {"buy", "long"}:
        return SignalSide.LONG
    if value in {"sell", "short"}:
        return SignalSide.SHORT
    raise ValueError("side must be long/buy or short/sell")


def normalize_symbol(raw: Any, default_symbol: str) -> str:
    value = str(raw or default_symbol).strip().upper()
    if not value:
        raise ValueError("symbol or ticker is required")

    if ":" in value and "/" not in value.split(":", 1)[0]:
        value = value.split(":", 1)[-1]
    for suffix in (".P", ".PERP", "PERP"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]

    if "/" in value:
        if ":" in value:
            return value
        base, quote = value.split("/", 1)
        quote = quote.split(":", 1)[0]
        return f"{base}/{quote}:{quote}"

    compact = value.replace("-", "").replace("_", "")
    for quote in QUOTE_ASSETS:
        if compact.endswith(quote) and len(compact) > len(quote):
            base = compact[: -len(quote)]
            return f"{base}/{quote}:{quote}"

    raise ValueError(f"cannot normalize TradingView symbol/ticker: {raw}")


def alert_from_payload(payload: dict[str, Any]) -> TradingAlert:
    settings = load_settings()
    symbol = normalize_symbol(payload.get("symbol") or payload.get("ticker"), settings.symbol)
    side = parse_side(payload.get("side", payload.get("side_code")))
    entry = _as_float(payload, "entry")
    take_profit = _as_float(payload, "tp")
    stop_loss = _as_float(payload, "sl")
    win_rate = _as_float(payload, "win_rate")
    win_loss_ratio = float(payload.get("win_loss_ratio") or payload.get("rr") or 1.5)
    signal_id = str(payload.get("signal_id") or "").strip()
    reason = str(payload.get("reason") or "TradingView webhook").strip()

    if not symbol:
        raise ValueError("symbol is required")
    if not signal_id:
        signal_id = f"{symbol}:{side.value}:{entry}:{take_profit}:{stop_loss}"
    if not 0 < win_rate <= 1:
        raise ValueError("win_rate must be between 0 and 1, for example 0.55")
    if win_loss_ratio <= 0:
        raise ValueError("rr/win_loss_ratio must be positive")
    if side == SignalSide.LONG and not stop_loss < entry < take_profit:
        raise ValueError("long signal requires sl < entry < tp")
    if side == SignalSide.SHORT and not take_profit < entry < stop_loss:
        raise ValueError("short signal requires tp < entry < sl")

    return TradingAlert(
        signal_id=signal_id,
        symbol=symbol,
        side=side,
        entry=entry,
        take_profit=take_profit,
        stop_loss=stop_loss,
        win_rate=win_rate,
        win_loss_ratio=win_loss_ratio,
        reason=reason,
    )


def signal_from_payload(payload: dict[str, Any]) -> tuple[str, Signal, float, float]:
    alert = alert_from_payload(payload)
    return alert.symbol, alert.to_signal(), alert.win_rate, alert.win_loss_ratio
