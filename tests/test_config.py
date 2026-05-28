import os
import importlib
import pytest
from unittest.mock import patch

def test_load_config_reads_required_env_vars():
    env = {
        "BINGX_API_KEY": "test_key",
        "BINGX_API_SECRET": "test_secret",
        "PUBSUB_PROJECT_ID": "my-project",
        "WEBHOOK_SECRET": "my_webhook_secret",
    }
    with patch.dict(os.environ, env, clear=True):
        importlib.invalidate_caches()
        from src.config import load_config
        cfg = load_config()
    assert cfg.bingx_api_key == "test_key"
    assert cfg.bingx_api_secret == "test_secret"
    assert cfg.pubsub_project_id == "my-project"
    assert cfg.webhook_secret == "my_webhook_secret"

def test_load_config_applies_defaults():
    env = {
        "BINGX_API_KEY": "k",
        "BINGX_API_SECRET": "s",
        "PUBSUB_PROJECT_ID": "p",
        "WEBHOOK_SECRET": "w",
    }
    with patch.dict(os.environ, env, clear=True):
        importlib.invalidate_caches()
        from src.config import load_config
        cfg = load_config()
    assert cfg.bingx_mode == "demo"
    assert cfg.bingx_sandbox is True
    assert cfg.dry_run is True
    assert cfg.max_daily_loss_pct == 5.0
    assert cfg.max_open_positions == 5
    assert cfg.max_single_trade_pct == 10.0
    assert cfg.monitor_interval_sec == 30

def test_load_config_missing_required_raises():
    with patch.dict(os.environ, {}, clear=True):
        importlib.invalidate_caches()
        from src.config import load_config
        with pytest.raises(KeyError):
            load_config()
