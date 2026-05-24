import tempfile
import unittest
from pathlib import Path

from src.alerts import alert_from_payload
from src.config import Settings
from src.models import ManagedPosition, OrderResult, SignalSide
from src.position_store import ActivePositionStore
from src.strategy_executor import execute_alert_entry, monitor_active_positions_once, sync_positions_with_exchange


def _settings(path: str) -> Settings:
    return Settings(
        dry_run=True,
        environment="demo",
        api_key="",
        api_secret="",
        bingx_sandbox=True,
        bingx_api_base_url="",
        test_order_symbol="BTC/USDT:USDT",
        test_order_notional_usdt=5,
        execute_tradingview_orders=False,
        account_balance_asset="USDT",
        initial_margin_usdt=7,
        trade_margin_usdt=5,
        max_total_positions=7,
        target_wallet_balance_usdt=1000,
        active_positions_path=path,
        max_signal_age_seconds=30,
        min_win_rate=0.50,
        symbol="BTC/USDT:USDT",
        timeframe="5m",
        candle_limit=120,
        leverage=8,
        starting_equity_usdt=10,
        max_risk_per_trade_pct=0.02,
        max_kelly_fraction=0.05,
        max_daily_loss_usdt=2,
        fast_ema=9,
        slow_ema=21,
        take_profit_pct=0.015,
        stop_loss_pct=0.0075,
        estimated_win_rate=0.5,
        estimated_win_loss_ratio=1.5,
        trade_journal_path="data/trades.csv",
        webhook_host="127.0.0.1",
        webhook_port=8787,
        webhook_secret="",
        enforce_webhook_ip_allowlist=False,
        webhook_allowed_ips="",
        gcp_project_id="",
        pubsub_topic="tradingview-alerts",
        pubsub_subscription="tradingview-alerts-local-bot",
        cloud_run_host="0.0.0.0",
        cloud_run_port=8080,
    )


class FakeClient:
    def __init__(self) -> None:
        self.available_balance = 10.0
        self.total_balance = 10.0
        self.open_symbols: set[str] = set()
        self.last_price = 100.0
        self.closed_orders: list[tuple[str, SignalSide, float]] = []
        self.canceled_orders: list[tuple[str, str]] = []

    def fetch_total_balance(self, asset: str) -> float:
        return self.total_balance

    def fetch_available_balance(self, asset: str) -> float:
        return self.available_balance

    def fetch_open_position_symbols(self) -> set[str]:
        return set(self.open_symbols)

    def has_open_position(self, symbol: str, side: SignalSide) -> bool:
        return symbol in self.open_symbols

    def cancel_position_protection_orders(self, position: ManagedPosition) -> list[str]:
        canceled = []
        for order_id in (
            position.stop_loss_order_id,
            position.take_profit_1_order_id,
            position.take_profit_2_order_id,
        ):
            if order_id:
                self.canceled_orders.append((position.symbol, order_id))
                canceled.append(order_id)
        return canceled

    def calculate_quantity_from_notional(self, symbol: str, notional_usdt: float) -> tuple[float, float]:
        return notional_usdt / self.last_price, self.last_price

    def place_market_order_by_notional(
        self,
        symbol: str,
        side: SignalSide,
        notional_usdt: float,
        leverage: int,
    ) -> OrderResult:
        return OrderResult(order_id="entry-1", status="closed", message="filled")

    def fetch_ticker_last(self, symbol: str) -> float:
        return self.last_price

    def close_position_market(self, symbol: str, side: SignalSide, quantity: float) -> OrderResult:
        self.closed_orders.append((symbol, side, quantity))
        return OrderResult(order_id=f"close-{len(self.closed_orders)}", status="closed", message="closed")

    def place_reduce_only_trigger_market_order(
        self,
        symbol: str,
        side: SignalSide,
        quantity: float,
        trigger_price: float,
        trigger_kind: str,
    ) -> OrderResult:
        return OrderResult(order_id=f"{trigger_kind}-{quantity}", status="open", message="trigger")


class StrategyExecutorTest(unittest.TestCase):
    def test_execute_alert_entry_opens_fixed_notional_position(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            settings = _settings(path)
            client = FakeClient()
            store = ActivePositionStore(path)
            alert = alert_from_payload({
                "signal_id": "btc-long",
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "entry": 100,
                "tp": 110,
                "tp2": 120,
                "sl": 95,
                "win_rate": 0.55,
                "rr": 2.0,
            })

            result = execute_alert_entry(alert, settings, client, store)
            positions = store.load()

            self.assertTrue(result["opened"])
            self.assertEqual(result["notional_usdt"], 40)
            self.assertEqual(result["margin_usdt"], 5)
            self.assertEqual(positions[0].take_profit_1_price, 110)
            self.assertEqual(positions[0].take_profit_2_price, 120)
            self.assertTrue(positions[0].stop_loss_order_id.startswith("stop_loss"))
            self.assertTrue(positions[0].take_profit_1_order_id.startswith("take_profit"))
            self.assertTrue(positions[0].take_profit_2_order_id.startswith("take_profit"))

    def test_execute_alert_entry_rejects_insufficient_balance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            settings = _settings(path)
            client = FakeClient()
            client.available_balance = 4.99

            alert = alert_from_payload({
                "signal_id": "btc-long",
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "entry": 100,
                "tp": 110,
                "tp2": 120,
                "sl": 95,
                "win_rate": 0.55,
                "rr": 2.0,
            })

            result = execute_alert_entry(alert, settings, client, ActivePositionStore(path))

            self.assertFalse(result["opened"])
            self.assertEqual(result["reason"], "insufficient available balance")

    def test_execute_alert_entry_rejects_low_win_rate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            settings = _settings(path)
            alert = alert_from_payload({
                "signal_id": "btc-long",
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "entry": 100,
                "tp": 110,
                "tp2": 120,
                "sl": 95,
                "win_rate": 0.49,
                "rr": 2.0,
            })

            result = execute_alert_entry(alert, settings, FakeClient(), ActivePositionStore(path))

            self.assertFalse(result["opened"])
            self.assertEqual(result["reason"], "win_rate below minimum")
            self.assertEqual(result["min_win_rate"], 0.50)

    def test_monitor_closes_tp1_and_moves_stop_to_tp1(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            settings = _settings(path)
            client = FakeClient()
            client.open_symbols.add("BTC/USDT:USDT")
            client.last_price = 111
            store = ActivePositionStore(path)
            store.save([
                ManagedPosition(
                    signal_id="btc-long",
                    symbol="BTC/USDT:USDT",
                    side=SignalSide.LONG,
                    entry_price=100,
                    quantity=0.4,
                    remaining_quantity=0.4,
                    notional_usdt=40,
                    margin_usdt=5,
                    leverage=8,
                    stop_loss_price=95,
                    current_stop_loss_price=95,
                    take_profit_1_price=110,
                    take_profit_2_price=120,
                    tp1_closed=False,
                    closed=False,
                    entry_order_id="entry-1",
                )
            ])

            results = monitor_active_positions_once(settings, client, store)
            position = store.load()[0]

            self.assertEqual(results[0]["action"], "tp1_close_60pct_move_sl")
            self.assertAlmostEqual(client.closed_orders[0][2], 0.24)
            self.assertTrue(position.tp1_closed)
            self.assertEqual(position.current_stop_loss_price, 110)
            self.assertAlmostEqual(position.remaining_quantity, 0.16)

    def test_execute_alert_entry_rejects_expired_signal(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            settings = _settings(path)
            alert = alert_from_payload({
                "signal_id": "BTCUSDT.P-5-2020-01-01T00:00:00Z-manual-swift",
                "symbol": "BTC/USDT:USDT",
                "side": "long",
                "entry": 100,
                "tp": 110,
                "tp2": 120,
                "sl": 95,
                "win_rate": 0.55,
                "rr": 2.0,
            })

            result = execute_alert_entry(alert, settings, FakeClient(), ActivePositionStore(path))

            self.assertFalse(result["opened"])
            self.assertEqual(result["reason"], "signal expired")

    def test_sync_marks_missing_position_as_manually_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = str(Path(temp_dir) / "active.json")
            store = ActivePositionStore(path)
            store.save([
                ManagedPosition(
                    signal_id="btc-long",
                    symbol="BTC/USDT:USDT",
                    side=SignalSide.LONG,
                    entry_price=100,
                    quantity=0.4,
                    remaining_quantity=0.4,
                    notional_usdt=40,
                    margin_usdt=5,
                    leverage=8,
                    stop_loss_price=95,
                    current_stop_loss_price=95,
                    take_profit_1_price=110,
                    take_profit_2_price=120,
                    tp1_closed=False,
                    closed=False,
                    entry_order_id="entry-1",
                    stop_loss_order_id="sl-1",
                    take_profit_1_order_id="tp1-1",
                    take_profit_2_order_id="tp2-1",
                )
            ])
            client = FakeClient()

            results = sync_positions_with_exchange(client, store)
            position = store.load()[0]

            self.assertEqual(results[0]["action"], "position_missing_on_exchange")
            self.assertTrue(position.closed)
            self.assertEqual(position.status.value, "manually_closed")
            self.assertEqual(len(client.canceled_orders), 3)


if __name__ == "__main__":
    unittest.main()
