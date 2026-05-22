import unittest

from src.alerts import alert_from_payload, normalize_symbol
from src.webhook import _ip_allowed, _parse_side, _signal_from_payload
from src.models import SignalSide


class WebhookTest(unittest.TestCase):
    def test_parse_long_side(self) -> None:
        self.assertEqual(_parse_side("buy"), SignalSide.LONG)
        self.assertEqual(_parse_side("long"), SignalSide.LONG)

    def test_parse_short_side(self) -> None:
        self.assertEqual(_parse_side("sell"), SignalSide.SHORT)
        self.assertEqual(_parse_side("short"), SignalSide.SHORT)
        self.assertEqual(_parse_side("-1"), SignalSide.SHORT)

    def test_parse_long_side_code(self) -> None:
        self.assertEqual(_parse_side(1), SignalSide.LONG)
        self.assertEqual(_parse_side("1"), SignalSide.LONG)

    def test_ip_allowlist_accepts_tradingview_ip(self) -> None:
        allowed = "52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7"
        self.assertTrue(_ip_allowed("52.89.214.238", allowed))

    def test_ip_allowlist_rejects_unknown_ip(self) -> None:
        allowed = "52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7"
        self.assertFalse(_ip_allowed("203.0.113.10", allowed))

    def test_signal_payload_validates_long_levels(self) -> None:
        _, signal, win_rate, rr = _signal_from_payload({
            "signal_id": "btc-5m-1-long",
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "entry": 100,
            "tp": 110,
            "sl": 95,
            "win_rate": 0.55,
            "rr": 2.0,
        })
        self.assertEqual(signal.side, SignalSide.LONG)
        self.assertEqual(win_rate, 0.55)
        self.assertEqual(rr, 2.0)

    def test_alert_payload_preserves_signal_id(self) -> None:
        alert = alert_from_payload({
            "signal_id": "btc-5m-1-short",
            "symbol": "BTC/USDT:USDT",
            "side": "short",
            "entry": 100,
            "tp": 90,
            "sl": 105,
            "win_rate": 0.52,
            "rr": 1.8,
            "reason": "unit test",
        })

        self.assertEqual(alert.signal_id, "btc-5m-1-short")
        self.assertEqual(alert.side, SignalSide.SHORT)
        self.assertEqual(alert.take_profit, 90)
        self.assertEqual(alert.stop_loss, 105)

    def test_alert_event_uses_pubsub_shape(self) -> None:
        event = alert_from_payload({
            "signal_id": "btc-5m-2-long",
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "entry": 100,
            "tp": 110,
            "sl": 95,
            "win_rate": 0.55,
            "rr": 2.0,
        }).to_event(source_ip="52.89.214.238")

        self.assertEqual(event["signal_id"], "btc-5m-2-long")
        self.assertEqual(event["side"], "long")
        self.assertEqual(event["tp"], 110)
        self.assertEqual(event["sl"], 95)
        self.assertEqual(event["rr"], 2.0)
        self.assertEqual(event["source_ip"], "52.89.214.238")
        self.assertIn("received_at", event)

    def test_normalize_tradingview_usdt_perp_ticker(self) -> None:
        self.assertEqual(normalize_symbol("ETHUSDT.P", "BTC/USDT:USDT"), "ETH/USDT:USDT")
        self.assertEqual(normalize_symbol("BINANCE:SOLUSDT", "BTC/USDT:USDT"), "SOL/USDT:USDT")

    def test_alert_payload_accepts_ticker_without_symbol(self) -> None:
        alert = alert_from_payload({
            "signal_id": "eth-5m-1-long",
            "ticker": "ETHUSDT.P",
            "side": "long",
            "entry": 3500,
            "tp": 3600,
            "sl": 3450,
            "win_rate": 0.55,
            "rr": 2.0,
        })

        self.assertEqual(alert.symbol, "ETH/USDT:USDT")

    def test_alert_payload_accepts_side_code(self) -> None:
        alert = alert_from_payload({
            "signal_id": "swift-short",
            "symbol": "ETHUSDT.P",
            "side_code": -1,
            "entry": 3500,
            "tp": 3400,
            "sl": 3550,
            "win_rate": 0.55,
            "rr": 2.0,
        })

        self.assertEqual(alert.side, SignalSide.SHORT)
        self.assertEqual(alert.symbol, "ETH/USDT:USDT")


if __name__ == "__main__":
    unittest.main()
