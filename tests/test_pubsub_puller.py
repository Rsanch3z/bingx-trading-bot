import unittest

from src.pubsub_puller import process_payload


class PubSubPullerTest(unittest.TestCase):
    def test_process_payload_receives_alert_without_ordering(self) -> None:
        result = process_payload({
            "signal_id": "btc-5m-3-long",
            "symbol": "BTC/USDT:USDT",
            "side": "long",
            "entry": 100,
            "tp": 110,
            "sl": 95,
            "win_rate": 0.55,
            "rr": 2.0,
        })

        self.assertEqual(result["ok"], True)
        self.assertEqual(result["received"], True)
        self.assertEqual(result["signal_id"], "btc-5m-3-long")
        self.assertEqual(result["symbol"], "BTC/USDT:USDT")
        self.assertEqual(result["side"], "long")
        self.assertNotIn("order_id", result)
        self.assertNotIn("planned", result)


if __name__ == "__main__":
    unittest.main()
