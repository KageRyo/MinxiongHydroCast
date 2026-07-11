from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from floodcastminxiong.operations.health import (
    aggregate_health,
    assess_dataset,
    refresh_dataset_health,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
FIELDS = ["name", "observed_at"]


def record_at(timestamp: datetime) -> dict[str, object]:
    return {"name": "Minxiong", "observed_at": timestamp.isoformat(timespec="seconds")}


def test_assess_dataset_distinguishes_healthy_stale_and_demo():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    healthy = assess_dataset(
        [record_at(now - timedelta(minutes=5))],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=now,
    )
    stale = assess_dataset(
        [record_at(now - timedelta(minutes=31))],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=now,
    )
    demo = assess_dataset(
        [record_at(now)],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="demo",
        max_age_minutes=30,
        now=now,
    )

    assert healthy["state"] == "healthy"
    assert healthy["ready"] is True
    assert stale["state"] == "stale"
    assert stale["ready"] is False
    assert demo["state"] == "demo"
    assert demo["ready"] is False


def test_assess_dataset_reports_schema_drift():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    health = assess_dataset(
        [{"name": "Minxiong", "unexpected": "value"}],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=now,
    )

    assert health["state"] == "invalid"
    assert health["ready"] is False
    assert health["schema_errors"] == [
        "row 1: missing fields: observed_at",
        "row 1: unexpected fields: unexpected",
        "row 1: empty observed_at",
    ]


def test_refresh_dataset_health_becomes_stale_over_time():
    collected_at = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    health = assess_dataset(
        [record_at(collected_at)],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=collected_at,
    )

    refreshed = refresh_dataset_health(
        health,
        mode="live",
        now=collected_at + timedelta(minutes=31),
    )

    assert refreshed["state"] == "stale"
    assert refreshed["ready"] is False


def test_aggregate_health_requires_all_live_datasets_to_be_healthy():
    datasets = {
        "rain": {"health": {"state": "healthy"}},
        "flood": {"health": {"state": "stale"}},
    }

    assert aggregate_health(datasets, mode="live") == {
        "state": "unhealthy",
        "ready": False,
        "datasets": {"rain": "healthy", "flood": "stale"},
    }
