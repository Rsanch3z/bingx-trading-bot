import json
from concurrent.futures import TimeoutError

from google.cloud import pubsub_v1

from src.alerts import alert_from_payload
from src.config import load_settings


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
        "sl": alert.stop_loss,
        "win_rate": alert.win_rate,
        "rr": alert.win_loss_ratio,
    }


def run_puller() -> None:
    settings = load_settings()
    if not settings.gcp_project_id:
        raise ValueError("GCP_PROJECT_ID is required")

    subscriber = pubsub_v1.SubscriberClient()
    subscription = _subscription_path(settings.gcp_project_id, settings.pubsub_subscription)

    def callback(message: pubsub_v1.subscriber.message.Message) -> None:
        try:
            payload = json.loads(message.data.decode("utf-8"))
            result = process_payload(payload)
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
