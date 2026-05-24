import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.models import ManagedPosition, PositionStatus, SignalSide


class ActivePositionStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[ManagedPosition]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [self._from_dict(item) for item in data]

    def save(self, positions: list[ManagedPosition]) -> None:
        data = []
        for position in positions:
            item = asdict(position)
            item["side"] = position.side.value
            item["status"] = position.status.value
            data.append(item)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def upsert(self, position: ManagedPosition) -> None:
        positions = [item for item in self.load() if item.signal_id != position.signal_id]
        positions.append(position)
        self.save(positions)

    @staticmethod
    def _from_dict(item: dict[str, Any]) -> ManagedPosition:
        return ManagedPosition(
            signal_id=str(item["signal_id"]),
            symbol=str(item["symbol"]),
            side=SignalSide(str(item["side"])),
            entry_price=float(item["entry_price"]),
            quantity=float(item["quantity"]),
            remaining_quantity=float(item["remaining_quantity"]),
            notional_usdt=float(item["notional_usdt"]),
            margin_usdt=float(item["margin_usdt"]),
            leverage=int(item["leverage"]),
            stop_loss_price=float(item["stop_loss_price"]),
            current_stop_loss_price=float(item["current_stop_loss_price"]),
            take_profit_1_price=float(item["take_profit_1_price"]),
            take_profit_2_price=float(item["take_profit_2_price"]),
            tp1_closed=bool(item["tp1_closed"]),
            closed=bool(item["closed"]),
            entry_order_id=str(item["entry_order_id"]),
            stop_loss_order_id=str(item.get("stop_loss_order_id") or ""),
            take_profit_1_order_id=str(item.get("take_profit_1_order_id") or ""),
            take_profit_2_order_id=str(item.get("take_profit_2_order_id") or ""),
            status=PositionStatus(str(item.get("status") or PositionStatus.OPEN.value)),
            closed_reason=str(item.get("closed_reason") or ""),
            closed_at=str(item.get("closed_at") or ""),
        )
