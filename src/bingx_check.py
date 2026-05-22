from src.config import load_settings
from src.exchange import BingXClient


def run() -> None:
    settings = load_settings()
    client = BingXClient(
        settings.api_key,
        settings.api_secret,
        dry_run=False,
        sandbox=settings.bingx_sandbox,
        api_base_url=settings.bingx_api_base_url,
    )

    print(f"environment={settings.environment} sandbox={settings.bingx_sandbox}")
    print(f"symbol={settings.test_order_symbol}")

    quantity, last_price = client.calculate_quantity_from_notional(
        settings.test_order_symbol,
        settings.test_order_notional_usdt,
    )
    print(
        "market_check "
        f"last_price={last_price:.8f} "
        f"test_notional={settings.test_order_notional_usdt:.2f} "
        f"quantity={quantity:.8f}"
    )

    balance = client.fetch_balance()
    total = balance.get("total", {})
    free = balance.get("free", {})
    print(f"balance_total_usdt={total.get('USDT')}")
    print(f"balance_free_usdt={free.get('USDT')}")
    print(f"balance_total_vst={total.get('VST')}")
    print(f"balance_free_vst={free.get('VST')}")


if __name__ == "__main__":
    run()
