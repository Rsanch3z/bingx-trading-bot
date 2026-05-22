# Security Policy

## Secrets

Never commit:

- `.env` or `.env.*` files
- BingX API keys or secret keys
- TradingView webhook secrets
- Google Cloud project IDs tied to private deployments
- Cloud Run service URLs for live webhook receivers
- Google Cloud credential files
- trade journals, logs, or raw webhook payload captures

Use `.env.example` for placeholders only.

## API Key Permissions

For BingX keys:

- Start with VST/demo keys.
- Enable only read and futures trading permissions needed for testing.
- Do not enable withdrawal permissions.
- Do not enable transfer permissions unless explicitly required and reviewed.
- Use IP allowlists for production keys where possible.

## Webhook Exposure

Do not publish a live Cloud Run webhook URL in public documentation. Use placeholders such as:

```text
https://your-cloud-run-service-url/
```

Production receivers should use:

- a long random webhook secret
- TradingView source IP allowlist where practical
- replay protection / signal id deduplication
- request logging that redacts secrets

## Public Release Checks

Before making the repository public:

```bash
git log --all -- .env
git ls-files | grep -E '(^\.env$|data/|\.csv|key|secret)' || true
git grep -n "BINGX_API_KEY\|BINGX_API_SECRET\|WEBHOOK_SECRET" || true
```

Also enable GitHub secret scanning and push protection when available.

## Trading Risk

This project is experimental software. Live trading is at your own risk. Validate order behavior, TP/SL handling, position mode, fees, slippage, liquidation risk, and exchange-specific API behavior in demo before using real funds.
