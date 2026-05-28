import logging
import signal
import sys
from concurrent.futures import TimeoutError

from .bingx_executor import BingXExecutor, TradeSignal
from .config import load_config
from .position_monitor import PositionMonitor
from .pubsub_subscriber import PubSubSubscriber
from .risk_manager import RiskManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def run():
    config = load_config()
    executor = BingXExecutor(config)
    risk_manager = RiskManager(config)
    monitor = PositionMonitor(config, executor, risk_manager)

    logger.info("Starting BingX trading bot (mode=%s, dry_run=%s)", config.bingx_mode, config.dry_run)

    monitor.start()

    def on_signal(signal_: TradeSignal) -> bool:
        try:
            allowed, reason = risk_manager.evaluate(signal_)
            if not allowed:
                logger.warning("Trade rejected by risk manager: %s", reason)
                return True  # ACK to avoid infinite retry of rejected signals

            balance = executor.get_balance()

            if signal_.close_position:
                result = executor.close_position(signal_.symbol)
            else:
                result = executor.place_order(signal_, balance)

            logger.info("Trade result: %s", result)
            return True
        except Exception as exc:
            logger.error("Trade execution failed: %s", exc, exc_info=True)
            return False  # NACK — will retry

    subscriber = PubSubSubscriber(config, on_signal)
    streaming_pull = subscriber.start()

    def _shutdown(signum, frame):
        logger.info("Shutdown signal received, stopping...")
        monitor.stop()
        streaming_pull.cancel()
        streaming_pull.result(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Bot running. Press Ctrl+C to stop.")
    try:
        streaming_pull.result()
    except TimeoutError:
        streaming_pull.cancel()
        streaming_pull.result(timeout=5)


if __name__ == "__main__":
    run()
