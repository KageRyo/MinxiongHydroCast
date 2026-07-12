from typing import Any

import pytest

from floodcastminxiong.operations.alert_receiver import AlertmanagerWebhook
from floodcastminxiong.operations.discord_notifications import (
    FIRING_COLOR,
    DiscordDeliveryError,
    DiscordWebhookClient,
    build_discord_message,
)


def webhook_payload() -> dict[str, object]:
    return {
        "version": "4",
        "groupKey": '{}:{alertname="FloodCastNotReady"}',
        "status": "firing",
        "receiver": "operations-audit",
        "commonLabels": {"severity": "critical"},
        "commonAnnotations": {"summary": "FloodCast is not ready"},
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "FloodCastNotReady",
                    "severity": "critical",
                },
                "annotations": {"summary": "FloodCast is not ready"},
                "startsAt": "2026-07-12T10:00:00Z",
                "fingerprint": "fixture",
            }
        ],
    }


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload or {}

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def test_discord_message_is_bounded_and_disables_mentions():
    webhook = AlertmanagerWebhook.model_validate(webhook_payload())

    message = build_discord_message(webhook)

    assert message.username == "FloodCastMinxiong"
    assert message.allowed_mentions.parse == []
    assert message.embeds[0].color == FIRING_COLOR
    assert "FloodCastNotReady" in message.embeds[0].fields[0].name
    assert len(message.embeds[0].description) <= 800


def test_discord_message_stays_below_combined_embed_limit():
    payload = webhook_payload()
    template = payload["alerts"][0]
    payload["commonAnnotations"] = {"description": "d" * 10_000}
    payload["alerts"] = [
        {
            **template,
            "labels": {"alertname": "a" * 500, "severity": "critical"},
            "annotations": {"summary": "s" * 2_000},
            "fingerprint": str(index),
        }
        for index in range(50)
    ]

    embed = build_discord_message(AlertmanagerWebhook.model_validate(payload)).embeds[0]
    combined_length = (
        len(embed.title)
        + len(embed.description)
        + len(embed.footer.text)
        + sum(len(field.name) + len(field.value) for field in embed.fields)
    )

    assert len(embed.fields) == 9
    assert combined_length <= 6000


def test_discord_client_requires_official_https_webhook_url():
    with pytest.raises(ValueError, match="official HTTPS"):
        DiscordWebhookClient("https://example.test/api/webhooks/123/token")

    with pytest.raises(ValueError, match="official HTTPS"):
        DiscordWebhookClient("http://discord.com/api/webhooks/123/token")


def test_discord_client_waits_for_confirmation_without_exposing_mentions():
    session = FakeSession([FakeResponse(200, {"id": "message-123"})])
    client = DiscordWebhookClient(
        "https://discord.com/api/webhooks/123/secret-token?thread_id=456",
        session=session,
    )

    receipt = client.send(AlertmanagerWebhook.model_validate(webhook_payload()))

    assert receipt.message_id == "message-123"
    assert receipt.attempts == 1
    assert "wait=true" in session.calls[0]["url"]
    assert "thread_id=456" in session.calls[0]["url"]
    assert session.calls[0]["json"]["allowed_mentions"] == {"parse": []}
    assert session.calls[0]["timeout"] == 3


def test_discord_client_retries_rate_limit_with_bounded_delay():
    session = FakeSession(
        [
            FakeResponse(429, {"retry_after": 0.25}),
            FakeResponse(200, {"id": "message-456"}),
        ]
    )
    sleeps: list[float] = []
    client = DiscordWebhookClient(
        "https://discord.com/api/v10/webhooks/123/secret-token",
        session=session,
        sleep=sleeps.append,
    )

    receipt = client.send(AlertmanagerWebhook.model_validate(webhook_payload()))

    assert receipt.attempts == 2
    assert sleeps == [0.25]


def test_discord_client_returns_redacted_failure_code():
    session = FakeSession([FakeResponse(401)])
    client = DiscordWebhookClient(
        "https://discord.com/api/webhooks/123/secret-token",
        session=session,
    )

    with pytest.raises(DiscordDeliveryError) as error:
        client.send(AlertmanagerWebhook.model_validate(webhook_payload()))

    assert error.value.reason == "http_401"
    assert "secret-token" not in str(error.value)
