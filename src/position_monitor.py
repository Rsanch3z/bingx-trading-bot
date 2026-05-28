import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from .bingx_executor import BingXExecutor
from .config import Config
from .risk_manager import RiskManager

logger = logging.getLogger(__name__)

PROGRESS_FILE = Path(__file__).parent.parent / "PROGRESS.md"
BOT_STATUS_MARKER = "## Bot 狀態（由 position_monitor 自動更新）"


class PositionMonitor:
    def __init__(self, config: Config, executor: BingXExecutor, risk_manager: RiskManager):
        self.config = config
        self.executor = executor
        self.risk_manager = risk_manager
        self._stop_event = threading.Event()

    def _update_progress_md(self, positions: list, balance: float, daily_loss_pct: float):
        try:
            content = PROGRESS_FILE.read_text(encoding="utf-8")
            marker_idx = content.find(BOT_STATUS_MARKER)
            if marker_idx == -1:
                return

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status_block = f"""{BOT_STATUS_MARKER}

_最後更新: {now}_

**帳戶餘額:** {balance:.2f} USDT
**當日已虧:** {daily_loss_pct:.2f}%
**熔斷狀態:** {"🔴 觸發" if self.risk_manager.state.circuit_breaker_active else "🟢 正常"}
**持倉數量:** {len(positions)}

| Symbol | Side | Qty | UnrealPnL |
|--------|------|-----|-----------|
"""
            for pos in positions:
                status_block += (
                    f"| {pos.get('symbol')} "
                    f"| {pos.get('positionSide')} "
                    f"| {pos.get('positionAmt')} "
                    f"| {pos.get('unrealizedProfit', '—')} |\n"
                )

            new_content = content[:marker_idx] + status_block
            PROGRESS_FILE.write_text(new_content, encoding="utf-8")
        except Exception as exc:
            logger.error("Failed to update PROGRESS.md: %s", exc)

    def _poll(self):
        try:
            balance = self.executor.get_balance()
            positions = self.executor.get_open_positions()
            position_count = len(positions)
            self.risk_manager.update_position_count(position_count)
            daily_loss = self.risk_manager.state.daily_realized_loss_pct
            self._update_progress_md(positions, balance, daily_loss)
            logger.debug("Monitor: %d positions, balance %.2f", position_count, balance)
        except Exception as exc:
            logger.error("Position monitor poll error: %s", exc)

    def start(self):
        def _loop():
            while not self._stop_event.is_set():
                self._poll()
                self._stop_event.wait(timeout=self.config.monitor_interval_sec)

        thread = threading.Thread(target=_loop, name="position-monitor", daemon=True)
        thread.start()
        logger.info("Position monitor started (interval: %ds)", self.config.monitor_interval_sec)
        return thread

    def stop(self):
        self._stop_event.set()
