"""Freshness and schema-health contracts for operational datasets."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIPEI_TZ)
    return parsed


def schema_fingerprint(fieldnames: list[str]) -> str:
    encoded = json.dumps(fieldnames, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assess_dataset(
    records: list[dict[str, object]],
    *,
    fieldnames: list[str],
    timestamp_field: str,
    mode: str,
    max_age_minutes: float,
    now: datetime,
    empty_observed_at: str | None = None,
    freshness_observed_at: str | None = None,
) -> dict[str, Any]:
    expected = set(fieldnames)
    schema_errors: list[str] = []
    timestamps: list[datetime] = []

    if not records and empty_observed_at is None:
        schema_errors.append("dataset contains no records")
    elif not records:
        try:
            timestamps.append(parse_timestamp(empty_observed_at))
        except (TypeError, ValueError):
            schema_errors.append(f"invalid empty observation timestamp: {empty_observed_at}")

    for index, record in enumerate(records, start=1):
        actual = set(record)
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        if missing:
            schema_errors.append(f"row {index}: missing fields: {', '.join(missing)}")
        if unexpected:
            schema_errors.append(f"row {index}: unexpected fields: {', '.join(unexpected)}")
        raw_timestamp = str(record.get(timestamp_field, "")).strip()
        if not raw_timestamp:
            schema_errors.append(f"row {index}: empty {timestamp_field}")
            continue
        try:
            timestamps.append(parse_timestamp(raw_timestamp))
        except ValueError:
            schema_errors.append(f"row {index}: invalid {timestamp_field}: {raw_timestamp}")

    if freshness_observed_at is not None:
        try:
            timestamps = [parse_timestamp(freshness_observed_at)]
        except (TypeError, ValueError):
            schema_errors.append(f"invalid freshness timestamp: {freshness_observed_at}")

    observed_at = max(timestamps).isoformat(timespec="seconds") if timestamps else ""
    age_minutes: float | None = None
    if timestamps:
        age_minutes = max(0.0, (now - max(timestamps)).total_seconds() / 60)

    if schema_errors:
        state = "invalid"
    elif mode == "demo":
        state = "demo"
    elif age_minutes is None or age_minutes > max_age_minutes:
        state = "stale"
    else:
        state = "healthy"

    return {
        "state": state,
        "ready": state == "healthy",
        "observed_at": observed_at,
        "age_minutes": round(age_minutes, 3) if age_minutes is not None else None,
        "max_age_minutes": max_age_minutes,
        "schema_sha256": schema_fingerprint(fieldnames),
        "schema_errors": schema_errors,
    }


def refresh_dataset_health(
    health: dict[str, Any],
    *,
    mode: str,
    now: datetime,
) -> dict[str, Any]:
    refreshed = dict(health)
    if health.get("schema_errors"):
        refreshed["state"] = "invalid"
        refreshed["ready"] = False
        return refreshed
    if mode == "demo":
        refreshed["state"] = "demo"
        refreshed["ready"] = False
        return refreshed

    degradation_reasons = list(health.get("degradation_reasons", []))
    persistent_state = health.get("persistent_state")
    observed_at = str(health.get("observed_at", ""))
    try:
        age_minutes = max(0.0, (now - parse_timestamp(observed_at)).total_seconds() / 60)
    except (TypeError, ValueError):
        age_minutes = None
    max_age_minutes = float(health.get("max_age_minutes", 0))
    refreshed["age_minutes"] = round(age_minutes, 3) if age_minutes is not None else None
    if age_minutes is None or age_minutes > max_age_minutes:
        refreshed["state"] = "stale"
        refreshed["ready"] = False
    elif persistent_state in {
        "stale",
        "degraded",
        "upstream_unhealthy",
        "coverage_missing",
    }:
        refreshed["state"] = persistent_state
        refreshed["ready"] = False
    elif degradation_reasons:
        refreshed["state"] = "degraded"
        refreshed["ready"] = False
    else:
        refreshed["state"] = "healthy"
        refreshed["ready"] = True
    return refreshed


def aggregate_health(
    datasets: dict[str, dict[str, Any]],
    *,
    mode: str,
) -> dict[str, Any]:
    states = {name: str(details.get("health", {}).get("state", "invalid")) for name, details in datasets.items()}
    if not datasets:
        state = "unavailable"
    elif mode == "demo":
        state = "demo"
    elif all(value == "healthy" for value in states.values()):
        state = "healthy"
    else:
        state = "unhealthy"
    return {
        "state": state,
        "ready": state == "healthy",
        "datasets": states,
    }
