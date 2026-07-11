import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from floodcastminxiong.operations.shadow import ShadowCriteria, evaluate_shadow
from floodcastminxiong.operations.snapshot_store import DatasetPayload, SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def publish_ready_snapshot(store: SnapshotStore, completed_at: datetime) -> None:
    observed_at = completed_at.isoformat(timespec="seconds")
    health = {
        "state": "healthy",
        "ready": True,
        "observed_at": observed_at,
        "age_minutes": 0,
        "max_age_minutes": 30,
        "schema_sha256": "fixture",
        "schema_errors": [],
    }
    store.publish(
        mode="live",
        started_at=observed_at,
        completed_at=observed_at,
        datasets=[
            DatasetPayload(
                name="rain_gauges",
                product_type="official_observation",
                records=[{"station": "Minxiong", "observed_at": observed_at}],
                fieldnames=["station", "observed_at"],
                health=health,
            )
        ],
        health={
            "state": "healthy",
            "ready": True,
            "datasets": {"rain_gauges": "healthy"},
        },
        now=completed_at,
    )


def evidence_file(tmp_path, start_at: datetime, end_at: datetime):
    path = tmp_path / "shadow_evidence.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "heavy_rain_periods": [
                    {
                        "event_id": "minxiong_heavy_rain",
                        "start_at": start_at.isoformat(),
                        "end_at": end_at.isoformat(),
                        "source": "official-report-reference",
                        "reviewed_by": "operator@example.test",
                        "confirmed": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def passing_criteria() -> ShadowCriteria:
    return ShadowCriteria(
        lookback_hours=1,
        minimum_duration_hours=0.3,
        minimum_live_attempts=3,
        minimum_success_rate=1,
        minimum_readiness_rate=1,
        maximum_gap_minutes=10,
        required_heavy_rain_periods=1,
    )


def test_shadow_gate_requires_continuous_live_coverage_and_reviewed_event(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    for minutes in (0, 10, 20):
        publish_ready_snapshot(store, start + timedelta(minutes=minutes))

    report = evaluate_shadow(
        store,
        evidence_path=evidence_file(tmp_path, start, start + timedelta(minutes=20)),
        criteria=passing_criteria(),
        now=start + timedelta(minutes=20),
    )

    assert report["shadow_gate_passed"] is True
    assert report["metrics"]["live_attempts"] == 3
    assert report["metrics"]["covered_heavy_rain_periods"] == 1
    assert report["notification_allowed"] is False
    assert report["notification_blockers"] == [
        "notification delivery and local model-label gates are not implemented"
    ]


def test_shadow_gate_fails_without_reviewed_heavy_rain_evidence(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    for minutes in (0, 10, 20):
        publish_ready_snapshot(store, start + timedelta(minutes=minutes))

    report = evaluate_shadow(
        store,
        evidence_path=tmp_path / "missing.json",
        criteria=passing_criteria(),
        now=start + timedelta(minutes=20),
    )

    assert report["shadow_gate_passed"] is False
    assert report["checks"]["heavy_rain_periods"] is False
    assert report["checks"]["evidence_valid"] is False
    assert report["notification_allowed"] is False


def test_shadow_gate_counts_failed_live_attempts(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    for minutes in (0, 10, 20):
        publish_ready_snapshot(store, start + timedelta(minutes=minutes))
    failed_at = start + timedelta(minutes=15)
    store.publish_failure(
        mode="live",
        started_at=failed_at.isoformat(),
        completed_at=failed_at.isoformat(),
        failure_reason="source unavailable",
        now=failed_at,
    )

    report = evaluate_shadow(
        store,
        evidence_path=evidence_file(tmp_path, start, start + timedelta(minutes=20)),
        criteria=passing_criteria(),
        now=start + timedelta(minutes=20),
    )

    assert report["metrics"]["live_attempts"] == 4
    assert report["metrics"]["success_rate"] == 0.75
    assert report["checks"]["success_rate"] is False
    assert report["shadow_gate_passed"] is False
