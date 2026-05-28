import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    bingx_api_key: str
    bingx_api_secret: str
    bingx_mode: str
    bingx_sandbox: bool
    pubsub_project_id: str
    pubsub_subscription: str
    google_credentials: str
    webhook_secret: str
    max_daily_loss_pct: float
    max_open_positions: int
    max_single_trade_pct: float
    monitor_interval_sec: int
    dry_run: bool


def load_config() -> Config:
    return Config(
        bingx_api_key=os.environ["BINGX_API_KEY"],
        bingx_api_secret=os.environ["BINGX_API_SECRET"],
        bingx_mode=os.getenv("BINGX_MODE", "demo"),
        bingx_sandbox=os.getenv("BINGX_SANDBOX", "true").lower() == "true",
        pubsub_project_id=os.environ["PUBSUB_PROJECT_ID"],
        pubsub_subscription=os.getenv("PUBSUB_SUBSCRIPTION", "local-bot-sub"),
        google_credentials=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        webhook_secret=os.environ["WEBHOOK_SECRET"],
        max_daily_loss_pct=float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0")),
        max_open_positions=int(os.getenv("MAX_OPEN_POSITIONS", "5")),
        max_single_trade_pct=float(os.getenv("MAX_SINGLE_TRADE_PCT", "10.0")),
        monitor_interval_sec=int(os.getenv("MONITOR_INTERVAL_SEC", "30")),
        dry_run=os.getenv("DRY_RUN", "true").lower() == "true",
    )
