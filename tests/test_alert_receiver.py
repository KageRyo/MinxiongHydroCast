import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from floodcastminxiong.operations.alert_receiver import (
    AlertAuditLog,
    AlertmanagerWebhook,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def webhook_payload() -> dict[str, object]:
    return {
        "version": "4",
        "groupKey": '{}:{alertname="FloodCastNotReady"}',
        "truncatedAlerts": 0,
        "status": "firing",
        "receiver": "operations-audit",
        "groupLabels": {"alertname": "FloodCastNotReady"},
        "commonLabels": {"severity": "critical"},
        "commonAnnotations": {"summary": "FloodCast is not ready"},
        "externalURL": "http://127.0.0.1:9093",
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "FloodCastNotReady",
                    "severity": "critical",
                },
                "annotations": {"summary": "FloodCast is not ready"},
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
    assert persisted["receiver"] == "operations-audit"
    assert persisted["alerts"][0]["labels"]["severity"] == "critical"


def test_alertmanager_webhook_requires_at_least_one_alert():
    payload = webhook_payload()
    payload["alerts"] = []

    with pytest.raises(ValidationError):
        AlertmanagerWebhook.model_validate(payload)


def test_alertmanager_webhook_rejects_unknown_status():
    payload = webhook_payload()
    payload["status"] = "unknown"

    with pytest.raises(ValidationError):
        AlertmanagerWebhook.model_validate(payload)
