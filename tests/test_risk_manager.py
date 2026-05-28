import pytest
from datetime import date
from unittest.mock import patch
from src.config import Config
from src.bingx_executor import TradeSignal
from src.risk_manager import RiskManager


@pytest.fixture
def config():
    return Config(
        bingx_api_key="k", bingx_api_secret="s", bingx_mode="demo",
        bingx_sandbox=True, pubsub_project_id="p", pubsub_subscription="sub",
        google_credentials="", webhook_secret="w",
        max_daily_loss_pct=5.0, max_open_positions=3,
        max_single_trade_pct=10.0, monitor_interval_sec=30, dry_run=True,
    )


@pytest.fixture
def buy_signal():
    return TradeSignal(
        symbol="BTC-USDT", action="BUY", side="LONG", order_type="MARKET",
        size_pct=5.0, tp_pct=2.0, sl_pct=1.0, close_position=False,
        strategy="test", timestamp="2026-05-28T00:00:00Z",
    )


def test_normal_trade_passes(config, buy_signal):
    rm = RiskManager(config)
    rm.update_position_count(1)
    allowed, reason = rm.evaluate(buy_signal)
    assert allowed is True


def test_circuit_breaker_blocks_new_orders(config, buy_signal):
    rm = RiskManager(config)
    rm.update_daily_loss(6.0)  # over 5% limit
    allowed, reason = rm.evaluate(buy_signal)
    assert allowed is False
    assert "circuit breaker" in reason.lower()


def test_max_positions_blocks_new_orders(config, buy_signal):
    rm = RiskManager(config)
    rm.update_position_count(3)  # at limit
    allowed, reason = rm.evaluate(buy_signal)
    assert allowed is False
    assert "positions" in reason.lower()


def test_close_position_bypasses_all_checks(config):
    close_signal = TradeSignal(
        symbol="BTC-USDT", action="CLOSE", side="LONG", order_type="MARKET",
        size_pct=0, tp_pct=0, sl_pct=0, close_position=True,
        strategy="test", timestamp="2026-05-28T00:00:00Z",
    )
    rm = RiskManager(config)
    rm.update_daily_loss(99.0)   # circuit breaker active
    rm.update_position_count(99) # position limit exceeded
    allowed, reason = rm.evaluate(close_signal)
    assert allowed is True


def test_size_pct_clamped_to_max(config, buy_signal):
    buy_signal.size_pct = 50.0  # way over 10% limit
    rm = RiskManager(config)
    rm.evaluate(buy_signal)
    assert buy_signal.size_pct == 10.0


def test_daily_loss_resets_at_midnight(config, buy_signal):
    rm = RiskManager(config)
    rm.update_daily_loss(6.0)
    assert rm.state.circuit_breaker_active is True
    # simulate next day
    yesterday = date(2020, 1, 1)
    rm.state.last_reset_date = yesterday
    rm._reset_daily_if_needed()
    assert rm.state.circuit_breaker_active is False
    assert rm.state.daily_realized_loss_pct == 0.0
