import ipaddress
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.alerts import parse_side, signal_from_payload
from src.config import load_settings
from src.exchange import BingXClient
from src.journal import TradeJournal
from src.trading import execute_signal



def _client_ip(handler: BaseHTTPRequestHandler) -> str:
    cf_ip = handler.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()

    forwarded_for = handler.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()

    return str(handler.client_address[0])


def _ip_allowed(client_ip: str, allowed_ips: str) -> bool:
    try:
        ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    for raw in allowed_ips.split(","):
        item = raw.strip()
        if not item:
            continue
        try:
            if ip in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            if client_ip == item:
                return True
    return False

_parse_side = parse_side
_signal_from_payload = signal_from_payload


class TradingViewWebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        settings = load_settings()

        try:
            body_size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(body_size).decode("utf-8"))

            if settings.webhook_secret and payload.get("secret") != settings.webhook_secret:
                self._send_json(401, {"ok": False, "error": "invalid secret"})
                return

            client_ip = _client_ip(self)
            if settings.enforce_webhook_ip_allowlist and not _ip_allowed(client_ip, settings.webhook_allowed_ips):
                self._send_json(403, {"ok": False, "error": "source ip not allowed", "source_ip": client_ip})
                return

            symbol, signal, win_rate, win_loss_ratio = _signal_from_payload(payload)
            client = BingXClient(settings.api_key, settings.api_secret, dry_run=settings.dry_run)
            journal = TradeJournal(settings.trade_journal_path)
            equity = client.fetch_equity_usdt(settings.starting_equity_usdt)

            plan, order = execute_signal(
                client=client,
                journal=journal,
                symbol=symbol,
                signal=signal,
                equity_usdt=equity,
                win_rate=win_rate,
                win_loss_ratio=win_loss_ratio,
                max_kelly_fraction=settings.max_kelly_fraction,
                max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
                leverage=settings.leverage,
            )

            if plan is None or order is None:
                self._send_json(200, {"ok": True, "planned": False})
                return

            self._send_json(
                200,
                {
                    "ok": True,
                    "planned": True,
                    "dry_run": settings.dry_run,
                    "symbol": symbol,
                    "side": plan.side.value,
                    "quantity": plan.quantity,
                    "notional_usdt": plan.notional_usdt,
                    "risk_usdt": plan.risk_usdt,
                    "stop_loss": plan.stop_loss_price,
                    "take_profit": plan.take_profit_price,
                    "order_status": order.status,
                    "order_id": order.order_id,
                },
            )
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        print(format % args)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        response = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def run_server() -> None:
    settings = load_settings()
    server = HTTPServer((settings.webhook_host, settings.webhook_port), TradingViewWebhookHandler)
    print(f"TradingView webhook listening on http://{settings.webhook_host}:{settings.webhook_port}/")
    print(f"dry_run={settings.dry_run}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
