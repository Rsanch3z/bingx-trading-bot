import pytest
from unittest.mock import MagicMock, patch
from src.config import Config
from src.bingx_executor import BingXExecutor, TradeSignal


@pytest.fixture
def demo_config():
    return Config(
        bingx_api_key="test_key",
        bingx_api_secret="test_secret",
        bingx_mode="demo",
        bingx_sandbox=True,
        pubsub_project_id="p",
        pubsub_subscription="s",
        google_credentials="",
        webhook_secret="w",
        max_daily_loss_pct=5.0,
        max_open_positions=5,
        max_single_trade_pct=10.0,
        monitor_interval_sec=30,
        dry_run=True,
    )


@pytest.fixture
def live_config(demo_config):
    import dataclasses
    return dataclasses.replace(demo_config, dry_run=False, bingx_mode="live")


@pytest.fixture
def buy_signal():
    return TradeSignal(
        symbol="BTC-USDT",
        action="BUY",
        side="LONG",
        order_type="MARKET",
        size_pct=5.0,
        tp_pct=2.0,
        sl_pct=1.0,
        close_position=False,
        strategy="test",
        timestamp="2026-05-28T00:00:00Z",
    )


def test_dry_run_does_not_call_api(demo_config, buy_signal):
    executor = BingXExecutor(demo_config)
    with patch.object(executor, "_request") as mock_req:
        result = executor.place_order(buy_signal, balance=1000.0)
    mock_req.assert_not_called()
    assert result["dry_run"] is True


def test_place_order_calls_correct_endpoint(live_config, buy_signal):
    executor = BingXExecutor(live_config)
    mock_response = {"data": {"order": {"orderId": "123"}}, "code": 0}
    with patch.object(executor, "_request", return_value=mock_response) as mock_req:
        result = executor.place_order(buy_signal, balance=1000.0)
    mock_req.assert_called_once()
    call_args = mock_req.call_args
    assert call_args[0][0] == "POST"
    assert "/trade/order" in call_args[0][1]


def test_close_position_sends_opposite_side(live_config):
    executor = BingXExecutor(live_config)
    open_positions = [{"symbol": "BTCUSDT", "positionSide": "LONG", "positionAmt": "0.01"}]
    mock_response = {"data": {"order": {"orderId": "456"}}, "code": 0}
    with patch.object(executor, "get_open_positions", return_value=open_positions):
        with patch.object(executor, "_request", return_value=mock_response) as mock_req:
            result = executor.close_position("BTC-USDT")
    params = mock_req.call_args[0][2]  # positional: (method, path, params)
    assert params["side"] == "SELL"


def test_get_balance_parses_response(live_config):
    executor = BingXExecutor(live_config)
    mock_resp = {"data": {"balance": {"balance": "5000.00"}}, "code": 0}
    with patch.object(executor, "_request", return_value=mock_resp):
        bal = executor.get_balance()
    assert bal == 5000.0
