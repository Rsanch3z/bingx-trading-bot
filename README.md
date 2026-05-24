# BingX Trading Bot

Python-based BingX perpetual futures bot skeleton for validating TradingView alerts, receiving them through Google Cloud Pub/Sub, and placing small BingX VST/demo test orders.

This project is intentionally conservative:

- `DRY_RUN=true` by default.
- Secrets live in `.env`, which is ignored by git.
- TradingView alerts are received by Cloud Run and forwarded to Pub/Sub.
- The local puller consumes Pub/Sub messages.
- BingX test orders require explicit command-line confirmation.
- Current manual order mode uses fixed test notional, not Kelly sizing.

This is not investment advice. Leveraged perpetual futures can lose money quickly.

## Architecture

```text
TradingView alert
  -> Cloud Run webhook
  -> Pub/Sub topic
  -> local puller
  -> optional BingX VST/demo order command
```

Cloud Run should not need BingX API keys. The BingX API key stays local.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` locally. Do not commit it.

Important settings:

```env
DRY_RUN=true
ENVIRONMENT=demo

BINGX_API_KEY=
BINGX_API_SECRET=
BINGX_SANDBOX=true
BINGX_API_BASE_URL=https://open-api-vst.bingx.com

TEST_ORDER_SYMBOL=BTC/USDT:USDT
TEST_ORDER_NOTIONAL_USDT=5
LEVERAGE=8

EXECUTE_TRADINGVIEW_ORDERS=false
TRADE_MARGIN=5
MAX_TOTAL_POSITIONS=7
TARGET_WALLET_BALANCE=1000

WEBHOOK_SECRET=replace-with-a-long-random-secret
GCP_PROJECT_ID=
PUBSUB_TOPIC=tradingview-alerts
PUBSUB_SUBSCRIPTION=tradingview-alerts-local-bot
```

## TradingView Alert JSON

Use `ticker` for TradingView symbols. The receiver normalizes examples like `BTCUSDT.P` to `BTC/USDT:USDT`.

```json
{
  "secret": "your-webhook-secret",
  "signal_id": "{{ticker}}-{{interval}}-{{time}}-manual-swift",
  "symbol": "{{ticker}}",
  "side_code": 1,
  "side_note": "1=long,-1=short",
  "entry": 0.10603,
  "tp": 0.10613,
  "tp2": 0.10642,
  "sl": 0.10584,
  "win_rate": 0.7189,
  "rr": 0.5263,
  "reason": "TradingView alert"
}
```

Supported side fields:

- `side`: `long`, `short`, `buy`, or `sell`
- `side_code`: `1` for long, `-1` for short

If you use Pine Script, prefer `alert(payload, alert.freq_once_per_bar_close)` so TradingView sends real numeric values, not unresolved placeholders like `{{plot_28}}`.

More detail: [docs/tradingview_alert.md](docs/tradingview_alert.md).

## Cloud Run + Pub/Sub

Deploy Cloud Run and create Pub/Sub resources using:

[docs/cloud_run_pubsub.md](docs/cloud_run_pubsub.md)

After deployment, set the TradingView webhook URL to the Cloud Run service URL.

## Local Puller

Run the local puller to consume Pub/Sub messages:

```bash
.venv/bin/python -u -m src.pubsub_puller
```

Expected output:

```text
processed message_id=... result={'ok': True, 'received': True, 'signal_id': '...', 'symbol': 'BTC/USDT:USDT', ...}
```

## TradingView Order Execution

By default, the puller only receives and prints alerts. To enable BingX order execution from TradingView alerts, set:

```env
EXECUTE_TRADINGVIEW_ORDERS=true
DRY_RUN=false
TRADE_MARGIN=5
LEVERAGE=8
MAX_TOTAL_POSITIONS=7
TARGET_WALLET_BALANCE=1000
```

Current execution rules:

- available wallet balance must be at least `TRADE_MARGIN`
- notional size is fixed at `TRADE_MARGIN * LEVERAGE`
- the same symbol can have only one active position
- no more than `MAX_TOTAL_POSITIONS` symbols may be open
- reaching `TARGET_WALLET_BALANCE` logs a graduation signal instead of opening new trades
- alert payload must include `tp2` for staged exits

The entry executor stores active position state in `ACTIVE_POSITIONS_PATH`, defaulting to `data/active_positions.json`.

Run the monitor once to handle TP/SL exits:

```bash
.venv/bin/python -m src.monitor_positions
```

When price reaches TP1, the monitor closes 60% of the position and moves the tracked stop to TP1. When price reaches TP2, it closes the remaining 40%.

## BingX VST/Demo Checks

Check BingX VST/demo connectivity without placing an order:

```bash
.venv/bin/python -m src.bingx_check
```

This prints market precision, the quantity for `TEST_ORDER_NOTIONAL_USDT`, and VST balance.

## Manual BingX Test Order

Manual orders are protected by two switches:

- `.env` must be overridden with `DRY_RUN=false`
- `CONFIRM_BINGX_ORDER=yes` must be present

Example: place a small VST/demo long market order with TP/SL at +/- 50% from the reference price:

```bash
DRY_RUN=false \
CONFIRM_BINGX_ORDER=yes \
TEST_ORDER_SIDE=long \
TEST_ORDER_TP_PCT=0.5 \
TEST_ORDER_SL_PCT=0.5 \
.venv/bin/python -m src.bingx_test_order
```

Keep `TEST_ORDER_NOTIONAL_USDT` small until the full path is verified.

## Safety

- Never commit `.env`.
- Never commit real Cloud Run URLs, GCP project IDs, API keys, webhook secrets, logs, or trade journals.
- Use BingX VST/demo keys first.
- Do not enable withdrawal permissions on API keys.
- Do not enable transfer permissions unless you have a specific, reviewed reason.
- Keep `DRY_RUN=true` unless you are intentionally testing an order.
- Prefer IP allowlists for production API keys.
- Verify TP/SL behavior in demo before using live funds.
- Live trading is at your own risk. Review exchange behavior, fees, slippage, liquidation risk, and all order parameters before using real funds.

## Public Release Checklist

Before making a repository public, run:

```bash
git log --all -- .env
git ls-files | grep -E '(^\.env$|data/|\.csv|key|secret)' || true
git grep -n "BINGX_API_KEY\|BINGX_API_SECRET\|WEBHOOK_SECRET" || true
```

Expected outcome:

- `.env` has never been committed.
- `data/`, CSV journals, and local logs are not tracked.
- Any API key or secret hits are placeholders, documentation examples, or environment variable names only.
- Cloud Run webhook URLs are placeholders, not live deployment URLs.

Enable GitHub secret scanning and push protection before public release when available for the repository/account.

## Tests

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Current scope covers alert parsing, TradingView payload tolerance, symbol normalization, webhook helpers, and Kelly sizing basics.
