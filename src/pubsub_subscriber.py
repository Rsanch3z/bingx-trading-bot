import json
import logging
from typing import Callable

from google.cloud import pubsub_v1

from .bingx_executor import TradeSignal
from .config import Config

logger = logging.getLogger(__name__)


def _parse_message(data: bytes) -> TradeSignal:
    payload = json.loads(data.decode("utf-8"))
    return TradeSignal(
        symbol=payload["symbol"],
        action=payload["action"],
        side=payload.get("side", "LONG"),
        order_type=payload.get("order_type", "MARKET"),
        size_pct=float(payload.get("size_pct", 1.0)),
        tp_pct=float(payload.get("tp_pct", 0.0)),
        sl_pct=float(payload.get("sl_pct", 0.0)),
        close_position=bool(payload.get("close_position", False)),
        strategy=payload.get("strategy", ""),
        timestamp=payload.get("timestamp", ""),
    )


class PubSubSubscriber:
    def __init__(self, config: Config, on_signal: Callable[[TradeSignal], bool]):
        self.config = config
        self.on_signal = on_signal
        self._client = pubsub_v1.SubscriberClient()
        self._subscription_path = self._client.subscription_path(
            config.pubsub_project_id, config.pubsub_subscription
        )

    def _callback(self, message: pubsub_v1.types.ReceivedMessage):
        try:
            signal = _parse_message(message.data)
            logger.info("Signal received: %s %s", signal.action, signal.symbol)
            success = self.on_signal(signal)
            if success:
                message.ack()
                logger.info("Message ACKed")
            else:
                message.nack()
                logger.warning("Message NACKed — will retry")
        except Exception as exc:
            logger.error("Failed to process message: %s", exc)
            message.nack()

    def start(self):
        streaming_pull = self._client.subscribe(
            self._subscription_path, callback=self._callback
        )
        logger.info("Listening on %s ...", self._subscription_path)
        return streaming_pull
