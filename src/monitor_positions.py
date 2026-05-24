from src.config import load_settings
from src.exchange import BingXClient
from src.position_store import ActivePositionStore
from src.strategy_executor import monitor_active_positions_once


def run() -> None:
    settings = load_settings()
    client = BingXClient(
        settings.api_key,
        settings.api_secret,
        dry_run=settings.dry_run,
        sandbox=settings.bingx_sandbox,
        api_base_url=settings.bingx_api_base_url,
    )
    store = ActivePositionStore(settings.active_positions_path)
    results = monitor_active_positions_once(settings, client, store)
    if not results:
        print("no position exits triggered")
        return
    for result in results:
        print(f"position_exit result={result}")


if __name__ == "__main__":
    run()
