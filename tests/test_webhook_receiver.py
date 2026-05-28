import json
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

VALID_SECRET = "test_secret_abc123"


@pytest.fixture
def client():
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "cloud", "webhook_receiver"))
    with patch.dict(os.environ, {
        "WEBHOOK_SECRET": VALID_SECRET,
        "PUBSUB_PROJECT_ID": "test-project",
    }):
        with patch("google.cloud.pubsub_v1.PublisherClient"):  # block module-level client init
            import importlib
            import main as receiver
            importlib.reload(receiver)
            yield TestClient(receiver.app)


def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_alert_rejects_wrong_secret(client):
    payload = {"secret": "wrong", "symbol": "BTC-USDT", "action": "BUY"}
    resp = client.post("/alert", json=payload)
    assert resp.status_code == 403


def test_alert_accepts_valid_secret_and_publishes(client):
    payload = {
        "secret": VALID_SECRET,
        "symbol": "BTC-USDT",
        "action": "BUY",
        "side": "LONG",
        "order_type": "MARKET",
        "size_pct": 5.0,
        "tp_pct": 2.0,
        "sl_pct": 1.0,
        "close_position": False,
        "strategy": "test",
        "timestamp": "2026-05-28T00:00:00Z",
    }
    mock_future = MagicMock()
    mock_future.result.return_value = "msg_id_123"

    with patch("main.publisher") as mock_pub:
        mock_pub.topic_path.return_value = "projects/test-project/topics/tradingview-alerts"
        mock_pub.publish.return_value = mock_future
        resp = client.post("/alert", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    published = json.loads(mock_pub.publish.call_args[0][1].decode())
    assert "secret" not in published
    assert published["symbol"] == "BTC-USDT"


def test_alert_returns_500_on_publish_failure(client):
    payload = {
        "secret": VALID_SECRET,
        "symbol": "BTC-USDT",
        "action": "BUY",
        "side": "LONG",
        "order_type": "MARKET",
        "size_pct": 5.0,
        "tp_pct": 2.0,
        "sl_pct": 1.0,
        "close_position": False,
        "strategy": "test",
        "timestamp": "2026-05-28T00:00:00Z",
    }
    mock_future = MagicMock()
    mock_future.result.side_effect = Exception("Pub/Sub unavailable")

    with patch("main.publisher") as mock_pub:
        mock_pub.topic_path.return_value = "projects/test-project/topics/tradingview-alerts"
        mock_pub.publish.return_value = mock_future
        resp = client.post("/alert", json=payload)

    assert resp.status_code == 500
