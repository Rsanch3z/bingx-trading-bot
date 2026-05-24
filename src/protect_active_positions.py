from src.config import load_settings
from src.exchange import BingXClient
from src.position_store import ActivePositionStore
from src.strategy_executor import ensure_exchange_protection


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
    updated = []
    for position in store.load():
        if position.closed:
            updated.append(position)
            continue
        try:
            protected_position, results = ensure_exchange_protection(position, client)
            updated.append(protected_position)
            print(
                "protected_position "
                f"signal_id={position.signal_id} symbol={position.symbol} side={position.side.value} "
                f"orders={results}"
            )
        except Exception as exc:
            updated.append(position)
            print(
                "failed_protect_position "
                f"signal_id={position.signal_id} symbol={position.symbol} side={position.side.value} "
                f"error={exc}"
            )
    store.save(updated)


if __name__ == "__main__":
    run()
