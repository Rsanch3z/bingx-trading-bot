import json
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from src.alerts import alert_from_payload
from src.config import load_settings
from src.webhook import _client_ip, _ip_allowed


def _topic_path(project_id: str, topic: str) -> str:
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient.topic_path(project_id, topic)


def _publisher_client() -> Any:
    from google.cloud import pubsub_v1

    return pubsub_v1.PublisherClient()


def _redact_body(body: str) -> str:
    redacted = re.sub(r'("secret"\s*:\s*")[^"]*(")', r'\1***\2', body)
    redacted = re.sub(r"('secret'\s*:\s*')[^']*(')", r"\1***\2", redacted)
    redacted = re.sub(r"(\bsecret\s*:\s*)[^,}\s]+", r"\1***", redacted)
    return redacted[:500]


def _parse_request_body(body: str) -> dict[str, Any]:
    body = body.strip().lstrip("\ufeff")
    body = body.translate(str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"}))
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        repaired = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)", r'\1"\2"\3', body)
        repaired = re.sub(r"([{,]\s*)'([^']+)'(\s*:)", r'\1"\2"\3', repaired)
        repaired = re.sub(r":\s*'([^']*)'", r':"\1"', repaired)
        return json.loads(repaired)


class CloudRunReceiverHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"ok": True, "service": "cloud-run-receiver"})
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        settings = load_settings()

        try:
            if not settings.gcp_project_id:
                raise ValueError("GCP_PROJECT_ID is required")

            body_size = int(self.headers.get("Content-Length", "0"))
            content_type = self.headers.get("Content-Type", "")
            body = self.rfile.read(body_size).decode("utf-8")
            print(f"received body_size={body_size} content_type={content_type}")
            print(f"received body_preview={_redact_body(body)}")
            if not body.strip():
                raise ValueError("empty request body; TradingView alert Message must contain JSON")
            payload = _parse_request_body(body)

            if settings.webhook_secret and payload.get("secret") != settings.webhook_secret:
                print("rejected invalid_secret")
                self._send_json(401, {"ok": False, "error": "invalid secret"})
                return

            client_ip = _client_ip(self)
            if settings.enforce_webhook_ip_allowlist and not _ip_allowed(client_ip, settings.webhook_allowed_ips):
                print(f"rejected source_ip={client_ip} reason=source_ip_not_allowed")
                self._send_json(403, {"ok": False, "error": "source ip not allowed", "source_ip": client_ip})
                return

            alert = alert_from_payload(payload)
            event = alert.to_event(source_ip=client_ip)
            print(f"accepted signal_id={alert.signal_id} source_ip={client_ip} side={alert.side.value} symbol={alert.symbol}")

            publisher = _publisher_client()
            future = publisher.publish(
                _topic_path(settings.gcp_project_id, settings.pubsub_topic),
                json.dumps(event).encode("utf-8"),
            )

            self._send_json(
                200,
                {
                    "ok": True,
                    "published": True,
                    "signal_id": alert.signal_id,
                    "message_id": future.result(timeout=2),
                },
            )
        except Exception as exc:
            print(f"rejected error={exc}")
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
    server = HTTPServer((settings.cloud_run_host, settings.cloud_run_port), CloudRunReceiverHandler)
    print(f"Cloud Run receiver listening on http://{settings.cloud_run_host}:{settings.cloud_run_port}/")
    print(f"topic={settings.pubsub_topic}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
