import json
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1

from src.alerts import alert_from_payload
from src.config import load_settings
from src.exchange import BingXClient
from src.position_store import ActivePositionStore
from src.strategy_executor import execute_alert_entry


def _subscription_path(project_id: str, subscription: str) -> str:
    return pubsub_v1.SubscriberClient.subscription_path(project_id, subscription)


def process_payload(payload: dict) -> dict:
    alert = alert_from_payload(payload)
    return {
        "ok": True,
        "received": True,
        "signal_id": alert.signal_id,
        "symbol": alert.symbol,
        "side": alert.side.value,
        "entry": alert.entry,
        "tp": alert.take_profit,
        "tp2": alert.take_profit_2,
        "sl": alert.stop_loss,
        "win_rate": alert.win_rate,
        "rr": alert.win_loss_ratio,
    }


def execute_payload(payload: dict) -> dict:
    settings = load_settings()
    alert = alert_from_payload(payload)
    client = BingXClient(
        settings.api_key,
        settings.api_secret,
        dry_run=settings.dry_run,
        sandbox=settings.bingx_sandbox,
        api_base_url=settings.bingx_api_base_url,
    )
    store = ActivePositionStore(settings.active_positions_path)
    return execute_alert_entry(alert, settings, client, store)


def run_puller() -> None:
    settings = load_settings()
    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")

    subscriber = pubsub_v1.SubscriberClient()
    subscription = _subscription_path(settings.gcp_project_id, settings.pubsub_subscription)

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            payload = json.loads(message.data.decode("utf-8"))
            result = execute_payload(payload) if settings.execute_tradingview_orders else process_payload(payload)
            print(f"processed message_id={message.message_id} result={result}")
            message.ack()
        except Exception as exc:
            print(f"failed message_id={message.message_id} error={exc}")
            message.nack()

    streaming_pull = subscriber.subscribe(subscription, callback=callback)
    print(f"Pulling TradingView alerts from {subscription}")
    print(f"dry_run={settings.dry_run}")

    try:
        streaming_pull.result()
    except TimeoutError:
        streaming_pull.cancel()
        streaming_pull.result()


if __name__ == "__main__":
    run_puller()
