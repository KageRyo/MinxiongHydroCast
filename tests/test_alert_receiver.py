import json
import threading
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from minxionghydrocast.operations.alert_receiver import (
    AlertAuditLog,
    AlertmanagerWebhook,
    DeliveryAuditLog,
    handler_factory,
)
from minxionghydrocast.operations.discord_notifications import (
    DiscordDeliveryError,
    DiscordDeliveryReceipt,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def webhook_payload() -> dict[str, object]:
    return {
        "version": "4",
        "groupKey": '{}:{alertname="MinxiongHydroCastNotReady"}',
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "operations-audit",
        "groupLabels": {"alertname": "MinxiongHydroCastNotReady"},
        "commonLabels": {"severity": "critical"},
        "commonAnnotations": {"summary": "MinxiongHydroCast is not ready"},
        "externalURL": "http://127.0.0.1:9093",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "MinxiongHydroCastNotReady",
                    "severity": "critical",
                },
                "annotations": {"summary": "MinxiongHydroCast is not ready"},
                "startsAt": "2026-07-12T10:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "generatorURL": "http://127.0.0.1:9090/graph",
                "fingerprint": "fixture",
            }
        ],
    }


def test_alert_audit_log_validates_and_persists_webhook(tmp_path: Path):
    webhook = AlertmanagerWebhook.model_validate(webhook_payload())
    output = tmp_path / "notifications" / "alerts.jsonl"

    record = AlertAuditLog(output).append(
        webhook,
        now=datetime(2026, 7, 12, 18, 0, tzinfo=TAIPEI_TZ),
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert record["received_at"] == "2026-07-12T18:00:00+08:00"
    assert len(record["event_id"]) == 32
    assert persisted["receiver"] == "operations-audit"
    assert persisted["alerts"][0]["labels"]["severity"] == "critical"


def test_alertmanager_webhook_requires_at_least_one_alert():
    payload = webhook_payload()
    payload["alerts"] = []

    with pytest.raises(ValidationError):
        AlertmanagerWebhook.model_validate(payload)


def test_delivery_audit_log_persists_redacted_discord_result(tmp_path: Path):
    output = tmp_path / "notifications" / "discord-deliveries.jsonl"

    record = DeliveryAuditLog(output).append(
        event_id="event-123",
        status="failed",
        attempts=3,
        error_code="http_503",
        now=datetime(2026, 7, 12, 18, 5, tzinfo=TAIPEI_TZ),
    )

    persisted = json.loads(output.read_text(encoding="utf-8"))
    assert record["provider"] == "discord"
    assert persisted["status"] == "failed"
    assert persisted["error_code"] == "http_503"
    assert "webhook" not in persisted


def test_alertmanager_webhook_rejects_unknown_status():
    payload = webhook_payload()
    payload["status"] = "unknown"

    with pytest.raises(ValidationError):
        AlertmanagerWebhook.model_validate(payload)


class SuccessfulDiscordClient:
    def send(self, webhook: AlertmanagerWebhook) -> DiscordDeliveryReceipt:
        return DiscordDeliveryReceipt(attempts=1, message_id="message-123")


class FailedDiscordClient:
    def send(self, webhook: AlertmanagerWebhook) -> DiscordDeliveryReceipt:
        raise DiscordDeliveryError("http_503", attempts=2)


def post_alert(server: ThreadingHTTPServer) -> tuple[int, dict[str, object]]:
    body = json.dumps(webhook_payload()).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{server.server_port}/alerts",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.mark.parametrize(
    ("client", "expected_status", "delivery_status"),
    [
        (SuccessfulDiscordClient(), 202, "delivered"),
        (FailedDiscordClient(), 502, "failed"),
    ],
)
def test_alert_receiver_audits_discord_delivery(
    tmp_path: Path,
    client: object,
    expected_status: int,
    delivery_status: str,
):
    alert_output = tmp_path / "alerts.jsonl"
    delivery_output = tmp_path / "discord-deliveries.jsonl"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler_factory(
            AlertAuditLog(alert_output),
            discord_client=client,
            delivery_log=DeliveryAuditLog(delivery_output),
        ),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, response = post_alert(server)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    delivery = json.loads(delivery_output.read_text(encoding="utf-8"))
    alert = json.loads(alert_output.read_text(encoding="utf-8"))
    assert status == expected_status
    assert delivery["status"] == delivery_status
    assert delivery["event_id"] == alert["event_id"]
    assert "event_id" in response or response["discord"] == "delivered"
