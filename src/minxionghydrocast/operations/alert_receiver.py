"""Local Alertmanager webhook receiver with a durable audit log."""

from __future__ import annotations

import argparse
import json
import os
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from minxionghydrocast.operations.discord_notifications import (
    DiscordDeliveryError,
    DiscordWebhookClient,
)

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
            "event_id": uuid.uuid4().hex,
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


class DeliveryAuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append(
        self,
        *,
        event_id: str,
        status: Literal["delivered", "failed"],
        attempts: int,
        message_id: str = "",
        error_code: str = "",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        completed_at = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
        record = {
            "event_id": event_id,
            "provider": "discord",
            "status": status,
            "attempts": attempts,
            "message_id": message_id,
            "error_code": error_code,
            "completed_at": completed_at.isoformat(timespec="seconds"),
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


def handler_factory(
    audit_log: AlertAuditLog,
    *,
    discord_client: DiscordWebhookClient | None = None,
    delivery_log: DeliveryAuditLog | None = None,
):
    class AlertReceiverHandler(BaseHTTPRequestHandler):
        server_version = "MinxiongHydroCastAlertReceiver/1"

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
            except OSError:
                self._json(500, {"error": "alert audit persistence failed"})
                return
            if discord_client is not None:
                try:
                    receipt = discord_client.send(webhook)
                    if delivery_log is not None:
                        delivery_log.append(
                            event_id=record["event_id"],
                            status="delivered",
                            attempts=receipt.attempts,
                            message_id=receipt.message_id,
                        )
                except DiscordDeliveryError as exc:
                    try:
                        if delivery_log is not None:
                            delivery_log.append(
                                event_id=record["event_id"],
                                status="failed",
                                attempts=exc.attempts,
                                error_code=exc.reason,
                            )
                    except OSError:
                        self._json(500, {"error": "delivery audit persistence failed"})
                        return
                    self._json(
                        502,
                        {
                            "error": "Discord delivery failed",
                            "event_id": record["event_id"],
                        },
                    )
                    return
                except OSError:
                    self._json(500, {"error": "delivery audit persistence failed"})
                    return
            self._json(
                202,
                {
                    "status": "accepted",
                    "received_at": record["received_at"],
                    "alerts": len(webhook.alerts),
                    "discord": "delivered" if discord_client is not None else "disabled",
                },
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    return AlertReceiverHandler


def build_server(
    output: Path,
    *,
    host: str,
    port: int,
    discord_webhook_url: str | None = None,
    delivery_output: Path | None = None,
) -> ThreadingHTTPServer:
    discord_client = DiscordWebhookClient(discord_webhook_url) if discord_webhook_url else None
    delivery_log = DeliveryAuditLog(delivery_output) if delivery_output else None
    return ThreadingHTTPServer(
        (host, port),
        handler_factory(
            AlertAuditLog(output),
            discord_client=discord_client,
            delivery_log=delivery_log,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Receive Alertmanager webhooks into an audit log.")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delivery-output", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9087)
    args = parser.parse_args()
    discord_webhook_url = os.environ.get("MINXIONGHYDROCAST_DISCORD_WEBHOOK_URL", "").strip() or None
    delivery_output = args.delivery_output or args.output.with_name("discord-deliveries.jsonl")
    server = build_server(
        args.output,
        host=args.host,
        port=args.port,
        discord_webhook_url=discord_webhook_url,
        delivery_output=delivery_output,
    )
    discord_status = "enabled" if discord_webhook_url else "disabled"
    print(
        f"[OK] Alert receiver listening on http://{args.host}:{server.server_port} "
        f"discord={discord_status}"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
