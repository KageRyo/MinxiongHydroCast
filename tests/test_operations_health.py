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


def test_assess_dataset_accepts_expected_empty_feed_using_successful_fetch_time():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)

    health = assess_dataset(
        [],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=now,
        empty_observed_at=(now - timedelta(minutes=2)).isoformat(timespec="seconds"),
    )

    assert health["state"] == "healthy"
    assert health["ready"] is True
    assert health["observed_at"] == "2026-07-11T09:58:00+08:00"
    assert health["age_minutes"] == 2.0


def test_assess_dataset_can_use_source_selected_freshness_timestamp():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    health = assess_dataset(
        [record_at(now), record_at(now - timedelta(minutes=31))],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=now,
        freshness_observed_at=(now - timedelta(minutes=31)).isoformat(timespec="seconds"),
    )

    assert health["observed_at"] == "2026-07-11T09:29:00+08:00"
    assert health["state"] == "stale"


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


def test_refresh_dataset_health_preserves_collection_time_blocking_state():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    for persistent_state in (
        "stale",
        "degraded",
        "upstream_unhealthy",
        "coverage_missing",
    ):
        health = assess_dataset(
            [record_at(now)],
            fieldnames=FIELDS,
            timestamp_field="observed_at",
            mode="live",
            max_age_minutes=30,
            now=now,
        )
        health["state"] = persistent_state
        health["ready"] = False
        health["persistent_state"] = persistent_state

        refreshed = refresh_dataset_health(health, mode="live", now=now)

        assert refreshed["state"] == persistent_state
        assert refreshed["ready"] is False


def test_refresh_dataset_health_preserves_scraper_degradation():
    collected_at = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    health = assess_dataset(
        [record_at(collected_at)],
        fieldnames=FIELDS,
        timestamp_field="observed_at",
        mode="live",
        max_age_minutes=30,
        now=collected_at,
    )
    health["degradation_reasons"] = ["scraper_fallback"]

    refreshed = refresh_dataset_health(
        health,
        mode="live",
        now=collected_at + timedelta(minutes=5),
    )

    assert refreshed["state"] == "degraded"
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
