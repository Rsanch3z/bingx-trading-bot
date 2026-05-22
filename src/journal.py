import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from src.models import OrderResult, PositionPlan


@dataclass(frozen=True)
class TradeStats:
    total: int
    wins: int
    losses: int
    win_rate: float
    realized_pnl_usdt: float


class TradeJournal:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_open(self, plan: PositionPlan, order: OrderResult, reason: str) -> None:
        is_new = not self.path.exists()
        with self.path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self._fieldnames())
            if is_new:
                writer.writeheader()
            writer.writerow(
                {
                    "opened_at": datetime.now(timezone.utc).isoformat(),
                    "closed_at": "",
                    "side": plan.side.value,
                    "entry_price": plan.entry_price,
                    "exit_price": "",
                    "quantity": plan.quantity,
                    "notional_usdt": plan.notional_usdt,
                    "risk_usdt": plan.risk_usdt,
                    "stop_loss_price": plan.stop_loss_price,
                    "take_profit_price": plan.take_profit_price,
                    "leverage": plan.leverage,
                    "order_id": order.order_id,
                    "status": order.status,
                    "reason": reason,
                    "pnl_usdt": "",
                    "result": "",
                }
            )

    def stats(self) -> TradeStats:
        if not self.path.exists():
            return TradeStats(total=0, wins=0, losses=0, win_rate=0.0, realized_pnl_usdt=0.0)

        total = wins = losses = 0
        pnl_total = 0.0
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                result = row.get("result", "")
                if not result:
                    continue
                total += 1
                pnl = float(row.get("pnl_usdt") or 0)
                pnl_total += pnl
                if result == "win":
                    wins += 1
                elif result == "loss":
                    losses += 1

        return TradeStats(
            total=total,
            wins=wins,
            losses=losses,
            win_rate=(wins / total) if total else 0.0,
            realized_pnl_usdt=pnl_total,
        )

    @staticmethod
    def _fieldnames() -> list[str]:
        return [
            "opened_at",
            "closed_at",
            "side",
            "entry_price",
            "exit_price",
            "quantity",
            "notional_usdt",
            "risk_usdt",
            "stop_loss_price",
            "take_profit_price",
            "leverage",
            "order_id",
            "status",
            "reason",
            "pnl_usdt",
            "result",
        ]
