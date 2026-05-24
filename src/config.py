from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw in (None, "") else int(raw)


@dataclass(frozen=True)
class Settings:
    dry_run: bool
    environment: str
    api_key: str
    api_secret: str
    bingx_sandbox: bool
    bingx_api_base_url: str
    test_order_symbol: str
    test_order_notional_usdt: float
    execute_tradingview_orders: bool
    account_balance_asset: str
    initial_margin_usdt: float
    trade_margin_usdt: float
    max_total_positions: int
    target_wallet_balance_usdt: float
    active_positions_path: str
    max_signal_age_seconds: int
    min_win_rate: float
    symbol: str
    timeframe: str
    candle_limit: int
    leverage: int
    starting_equity_usdt: float
    max_risk_per_trade_pct: float
    max_kelly_fraction: float
    max_daily_loss_usdt: float
    fast_ema: int
    slow_ema: int
    take_profit_pct: float
    stop_loss_pct: float
    estimated_win_rate: float
    estimated_win_loss_ratio: float
    trade_journal_path: str
    webhook_host: str
    webhook_port: int
    webhook_secret: str
    enforce_webhook_ip_allowlist: bool
    webhook_allowed_ips: str
    gcp_project_id: str
    pubsub_topic: str
    pubsub_subscription: str
    cloud_run_host: str
    cloud_run_port: int


def load_settings() -> Settings:
    return Settings(
        dry_run=_bool("DRY_RUN", True),
        environment=os.getenv("ENVIRONMENT", "demo"),
        api_key=os.getenv("BINGX_API_KEY", ""),
        api_secret=os.getenv("BINGX_API_SECRET", ""),
        bingx_sandbox=_bool("BINGX_SANDBOX", False),
        bingx_api_base_url=os.getenv("BINGX_API_BASE_URL", ""),
        test_order_symbol=os.getenv("TEST_ORDER_SYMBOL", os.getenv("SYMBOL", "BTC/USDT:USDT")),
        test_order_notional_usdt=_float("TEST_ORDER_NOTIONAL_USDT", 5.0),
        execute_tradingview_orders=_bool("EXECUTE_TRADINGVIEW_ORDERS", False),
        account_balance_asset=os.getenv("ACCOUNT_BALANCE_ASSET", "USDT"),
        initial_margin_usdt=_float("INITIAL_MARGIN", 7.0),
        trade_margin_usdt=_float("TRADE_MARGIN", 5.0),
        max_total_positions=_int("MAX_TOTAL_POSITIONS", 7),
        target_wallet_balance_usdt=_float("TARGET_WALLET_BALANCE", 1000.0),
        active_positions_path=os.getenv("ACTIVE_POSITIONS_PATH", "data/active_positions.json"),
        max_signal_age_seconds=_int("MAX_SIGNAL_AGE_SECONDS", 30),
        min_win_rate=_float("MIN_WIN_RATE", 0.50),
        symbol=os.getenv("SYMBOL", "BTC/USDT:USDT"),
        timeframe=os.getenv("TIMEFRAME", "5m"),
        candle_limit=_int("CANDLE_LIMIT", 120),
        leverage=_int("LEVERAGE", 1),
        starting_equity_usdt=_float("STARTING_EQUITY_USDT", 10.0),
        max_risk_per_trade_pct=_float("MAX_RISK_PER_TRADE_PCT", 0.02),
        max_kelly_fraction=_float("MAX_KELLY_FRACTION", 0.05),
        max_daily_loss_usdt=_float("MAX_DAILY_LOSS_USDT", 2.0),
        fast_ema=_int("FAST_EMA", 9),
        slow_ema=_int("SLOW_EMA", 21),
        take_profit_pct=_float("TAKE_PROFIT_PCT", 0.015),
        stop_loss_pct=_float("STOP_LOSS_PCT", 0.0075),
        estimated_win_rate=_float("ESTIMATED_WIN_RATE", 0.50),
        estimated_win_loss_ratio=_float("ESTIMATED_WIN_LOSS_RATIO", 1.50),
        trade_journal_path=os.getenv("TRADE_JOURNAL_PATH", "data/trades.csv"),
        webhook_host=os.getenv("WEBHOOK_HOST", "127.0.0.1"),
        webhook_port=_int("WEBHOOK_PORT", 8787),
        webhook_secret=os.getenv("WEBHOOK_SECRET", ""),
        enforce_webhook_ip_allowlist=_bool("ENFORCE_WEBHOOK_IP_ALLOWLIST", False),
        webhook_allowed_ips=os.getenv("WEBHOOK_ALLOWED_IPS", "52.89.214.238,34.212.75.30,54.218.53.128,52.32.178.7"),
        gcp_project_id=os.getenv("GCP_PROJECT_ID", ""),
        pubsub_topic=os.getenv("PUBSUB_TOPIC", "tradingview-alerts"),
        pubsub_subscription=os.getenv("PUBSUB_SUBSCRIPTION", "tradingview-alerts-local-bot"),
        cloud_run_host=os.getenv("CLOUD_RUN_HOST", "0.0.0.0"),
        cloud_run_port=_int("PORT", _int("CLOUD_RUN_PORT", 8080)),
    )
