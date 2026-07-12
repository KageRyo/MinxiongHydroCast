"""Local Alertmanager webhook receiver with a durable audit log."""

from __future__ import annotations

import argparse
import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
MAX_WEBHOOK_BYTES = 1024 * 1024


class AlertmanagerAlert(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    status: Literal["firing", "resolved"]
    labels: dict[str, str]
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str = ""
    endsAt: str = ""
    generatorURL: str = ""
    fingerprint: str = ""


class AlertmanagerWebhook(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    version: str
    groupKey: str = ""
    truncatedAlerts: int = Field(default=0, ge=0)
    status: Literal["firing", "resolved"]
    receiver: str
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    alerts: list[AlertmanagerAlert] = Field(min_length=1)


class AlertAuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(
        self,
        webhook: AlertmanagerWebhook,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        received_at = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
        record = {
            "received_at": received_at.isoformat(timespec="seconds"),
            **webhook.model_dump(),
        }
        encoded = (json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
            "utf-8"
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, self.path.open("ab") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        return record


def handler_factory(audit_log: AlertAuditLog):
    class AlertReceiverHandler(BaseHTTPRequestHandler):
        server_version = "FloodCastMinxiongAlertReceiver/1"

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._json(200, {"status": "ok"})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/alerts":
                self._json(404, {"error": "not found"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "invalid content length"})
                return
            if content_length < 1 or content_length > MAX_WEBHOOK_BYTES:
                self._json(413, {"error": "invalid payload size"})
                return
            try:
                raw = self.rfile.read(content_length)
                payload = json.loads(raw.decode("utf-8"))
                webhook = AlertmanagerWebhook.model_validate(payload)
                record = audit_log.append(webhook)
            except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
                self._json(400, {"error": "invalid alertmanager webhook", "detail": str(exc)})
                return
            self._json(
                202,
                {
                    "status": "accepted",
                    "received_at": record["received_at"],
                    "alerts": len(webhook.alerts),
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    return AlertReceiverHandler


def build_server(output: Path, *, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_factory(AlertAuditLog(output)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive Alertmanager webhooks into an audit log.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9087)
    args = parser.parse_args()
    server = build_server(args.output, host=args.host, port=args.port)
    print(f"[OK] Alert receiver listening on http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
