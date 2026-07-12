"""Optional Discord incoming-webhook delivery for operational alerts."""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
from pydantic import BaseModel, ConfigDict, Field

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DISCORD_HOST = "discord.com"
FIRING_COLOR = 0xD73A49
RESOLVED_COLOR = 0x2DA44E


class DiscordDeliveryError(RuntimeError):
    """A redacted Discord delivery failure safe to persist in an audit log."""

    def __init__(self, reason: str, *, attempts: int) -> None:
        super().__init__(reason)
        self.reason = reason
        self.attempts = attempts


class DiscordEmbedField(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1, max_length=256)
    value: str = Field(min_length=1, max_length=1024)
    inline: bool = False


class DiscordEmbedFooter(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    text: str = Field(min_length=1, max_length=2048)


class DiscordEmbed(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=4096)
    color: int = Field(ge=0, le=0xFFFFFF)
    fields: list[DiscordEmbedField] = Field(default_factory=list, max_length=25)
    footer: DiscordEmbedFooter
    timestamp: str


class DiscordAllowedMentions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parse: list[Literal["roles", "users", "everyone"]] = Field(default_factory=list)


class DiscordWebhookMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: str = Field(min_length=1, max_length=80)
    embeds: list[DiscordEmbed] = Field(min_length=1, max_length=10)
    allowed_mentions: DiscordAllowedMentions = Field(default_factory=DiscordAllowedMentions)


class DiscordDeliveryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: Literal["discord"] = "discord"
    attempts: int = Field(ge=1)
    message_id: str = ""


def _clip(value: str, limit: int) -> str:
    value = value.strip()
    if not value:
        return "n/a"
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _distinct(values: list[str]) -> str:
    return ", ".join(dict.fromkeys(value for value in values if value)) or "n/a"


def build_discord_message(webhook: Any, *, now: datetime | None = None) -> DiscordWebhookMessage:
    status = str(webhook.status)
    alert_count = len(webhook.alerts)
    received_at = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    common_summary = webhook.commonAnnotations.get("summary", "")
    common_description = webhook.commonAnnotations.get("description", "")
    description = (
        common_description
        or common_summary
        or (f"Alertmanager delivered {alert_count} operational alert(s).")
    )
    fields: list[DiscordEmbedField] = []
    for index, alert in enumerate(webhook.alerts[:8], start=1):
        alert_name = alert.labels.get("alertname", "unnamed alert")
        details = [
            f"Status: `{alert.status}`",
            f"Severity: `{alert.labels.get('severity', 'unknown')}`",
        ]
        if dataset := alert.labels.get("dataset"):
            details.append(f"Dataset: `{dataset}`")
        if instance := alert.labels.get("instance"):
            details.append(f"Instance: `{instance}`")
        if summary := alert.annotations.get("summary"):
            details.append(_clip(summary, 180))
        fields.append(
            DiscordEmbedField(
                name=_clip(f"{index}. {alert_name}", 100),
                value=_clip("\n".join(details), 300),
            )
        )
    if alert_count > len(fields):
        fields.append(
            DiscordEmbedField(
                name="Additional alerts",
                value=f"{alert_count - len(fields)} additional alert(s) omitted from this message.",
            )
        )
    severities = _distinct([alert.labels.get("severity", "unknown") for alert in webhook.alerts])
    return DiscordWebhookMessage(
        username="FloodCastMinxiong",
        embeds=[
            DiscordEmbed(
                title=_clip(
                    f"FloodCastMinxiong: {alert_count} alert(s) {status}",
                    256,
                ),
                description=_clip(description, 800),
                color=FIRING_COLOR if status == "firing" else RESOLVED_COLOR,
                fields=fields,
                footer=DiscordEmbedFooter(
                    text=_clip(f"Receiver: {webhook.receiver} | Severity: {severities}", 300)
                ),
                timestamp=received_at.isoformat(timespec="seconds"),
            )
        ],
    )


def _validated_endpoint(webhook_url: str) -> str:
    parsed = urlsplit(webhook_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    valid_path = (
        len(path_parts) in {4, 5}
        and path_parts[0] == "api"
        and (
            len(path_parts) == 4 or (path_parts[1].startswith("v") and path_parts[1][1:].isdigit())
        )
        and path_parts[-3] == "webhooks"
        and path_parts[-2].isdigit()
        and bool(path_parts[-1])
    )
    if (
        parsed.scheme != "https"
        or parsed.hostname != DISCORD_HOST
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or not valid_path
    ):
        raise ValueError("Discord webhook URL must be an official HTTPS incoming-webhook URL")
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["wait"] = "true"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), ""))


class DiscordWebhookClient:
    def __init__(
        self,
        webhook_url: str,
        *,
        timeout_seconds: float = 3,
        max_attempts: int = 2,
        session: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("Discord timeout must be positive")
        if max_attempts < 1 or max_attempts > 5:
            raise ValueError("Discord max_attempts must be between one and five")
        self._endpoint = _validated_endpoint(webhook_url)
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts
        self.session = session or requests.Session()
        self.sleep = sleep

    def send(self, webhook: Any) -> DiscordDeliveryReceipt:
        payload = build_discord_message(webhook).model_dump()
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self.session.post(
                    self._endpoint,
                    json=payload,
                    timeout=self.timeout_seconds,
                    headers={"User-Agent": "FloodCastMinxiong/0.1"},
                )
            except requests.RequestException as exc:
                if attempt == self.max_attempts:
                    raise DiscordDeliveryError(
                        f"transport_{type(exc).__name__}", attempts=attempt
                    ) from exc
                self.sleep(1)
                continue
            if 200 <= response.status_code < 300:
                try:
                    message_id = str(response.json().get("id", ""))
                except (ValueError, AttributeError):
                    message_id = ""
                return DiscordDeliveryReceipt(attempts=attempt, message_id=message_id)
            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == self.max_attempts:
                raise DiscordDeliveryError(f"http_{response.status_code}", attempts=attempt)
            delay = 1.0
            if response.status_code == 429:
                try:
                    delay = min(max(float(response.json().get("retry_after", delay)), 0), 1)
                except (ValueError, TypeError, AttributeError):
                    pass
            self.sleep(delay)
        raise AssertionError("unreachable Discord delivery state")
