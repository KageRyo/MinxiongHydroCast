import json
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from minxionghydrocast.operations.gap_incidents import (
    GapIncidentCriteria,
    build_gap_incident_report,
    main,
)
from minxionghydrocast.operations.snapshot_store import DatasetPayload, SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def publish_snapshot(
    store: SnapshotStore,
    completed_at: datetime,
    *,
    ready: bool,
    state: str = "healthy",
) -> None:
    observed_at = completed_at - (timedelta(minutes=90) if not ready else timedelta())
    dataset_health = {
        "state": state,
        "ready": ready,
        "observed_at": observed_at.isoformat(timespec="seconds"),
        "age_minutes": 90 if not ready else 0,
        "max_age_minutes": 30,
        "schema_sha256": "fixture",
        "schema_errors": [],
    }
    completed_at_text = completed_at.isoformat(timespec="seconds")
    store.publish(
        mode="live",
        started_at=completed_at_text,
        completed_at=completed_at_text,
        datasets=[
            DatasetPayload(
                name="flood_sensors",
                product_type="official_observation",
                records=[{"station": "Minxiong", "observed_at": observed_at.isoformat()}],
                fieldnames=["station", "observed_at"],
                health=dataset_health,
                source={
                    "authority": "Water Resources Agency, Taiwan",
                    "source_kind": "api",
                    "outcome": "ok" if ready else "stale",
                },
            )
        ],
        health={
            "state": "healthy" if ready else "unhealthy",
            "ready": ready,
            "datasets": {"flood_sensors": state},
        },
        metadata={
            "source_retries": {
                "flood_sensors": {"total": 0, "counts": []},
            }
        },
        now=completed_at,
    )


def criteria() -> GapIncidentCriteria:
    return GapIncidentCriteria(
        lookback_hours=2,
        maximum_gap_minutes=30,
    )


def test_gap_report_classifies_successful_stale_source_snapshots(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 26, 15, 10, tzinfo=TAIPEI_TZ)
    publish_snapshot(store, start, ready=True)
    publish_snapshot(
        store,
        start + timedelta(minutes=20),
        ready=False,
        state="stale",
    )
    publish_snapshot(store, start + timedelta(minutes=50), ready=True)

    report = build_gap_incident_report(
        store,
        criteria=criteria(),
        now=start + timedelta(minutes=50),
    )

    assert report["metrics"]["incidents_over_threshold"] == 1
    incident = report["incidents"][0]
    assert incident["duration_minutes"] == 50
    assert incident["classification"] == "source_data_stale"
    assert incident["successful_attempt_count"] == 1
    assert incident["has_readable_snapshot"] is True
    assert incident["sources"][0]["dataset"] == "flood_sensors"
    assert incident["alert"]["triggered"] is None
    assert incident["root_cause"]["status"] == "evidence_supported_local_cause"
    assert incident["fix"] is None
    assert incident["reproduced_by_test"] is None
    assert incident["manual_review"]["status"] == "pending"


def test_gap_report_distinguishes_no_completed_attempts(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 28, 15, 20, tzinfo=TAIPEI_TZ)
    publish_snapshot(store, start, ready=True)
    publish_snapshot(store, start + timedelta(minutes=43), ready=True)

    report = build_gap_incident_report(
        store,
        criteria=criteria(),
        now=start + timedelta(minutes=43),
    )

    incident = report["incidents"][0]
    assert incident["classification"] == "no_completed_attempts"
    assert incident["attempt_count"] == 0
    assert incident["has_successful_attempt"] is False
    assert incident["has_readable_snapshot"] is False
    assert incident["root_cause"]["status"] == "pending_journal_correlation"


def test_gap_report_classifies_failed_collection_attempts(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 23, 16, 30, tzinfo=TAIPEI_TZ)
    publish_snapshot(store, start, ready=True)
    failed_at = start + timedelta(minutes=20)
    store.publish_failure(
        mode="live",
        started_at=failed_at.isoformat(),
        completed_at=failed_at.isoformat(),
        failure_reason="official source returned invalid JSON",
        metadata={"failure_kind": "schema_drift"},
        now=failed_at,
    )
    publish_snapshot(store, start + timedelta(minutes=40), ready=True)

    report = build_gap_incident_report(
        store,
        criteria=criteria(),
        now=start + timedelta(minutes=40),
    )

    incident = report["incidents"][0]
    assert incident["classification"] == "collection_failure"
    assert incident["failed_attempt_count"] == 1
    assert incident["failure_kind_counts"] == {"schema_drift": 1}
    assert incident["attempts"][0]["failure_reason"] == (
        "official source returned invalid JSON"
    )


def test_gap_report_tracks_an_open_tail_without_mutating_history(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 29, 10, 0, tzinfo=TAIPEI_TZ)
    publish_snapshot(store, start, ready=True)
    manifest_paths_before = sorted(store.snapshots_dir.glob("*/manifest.json"))

    report = build_gap_incident_report(
        store,
        criteria=criteria(),
        now=start + timedelta(minutes=45),
    )

    assert report["incidents"][0]["open"] is True
    assert report["incidents"][0]["end_at"] == (
        start + timedelta(minutes=45)
    ).isoformat(timespec="seconds")
    assert sorted(store.snapshots_dir.glob("*/manifest.json")) == manifest_paths_before


def test_gap_report_does_not_flag_a_gap_at_the_threshold(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    start = datetime(2026, 7, 29, 10, 0, tzinfo=TAIPEI_TZ)
    publish_snapshot(store, start, ready=True)
    publish_snapshot(store, start + timedelta(minutes=30), ready=True)

    report = build_gap_incident_report(
        store,
        criteria=criteria(),
        now=start + timedelta(minutes=30),
    )

    assert report["metrics"]["maximum_gap_minutes"] == 30
    assert report["metrics"]["incidents_over_threshold"] == 0
    assert report["manual_review_required"] is False


def test_gap_incident_cli_writes_atomic_store_and_explicit_reports(
    tmp_path,
    monkeypatch,
):
    store_path = tmp_path / "operations"
    output = tmp_path / "reports" / "gap-incidents.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "minxiong-hydrocast-shadow-gap-incidents",
            "--store",
            str(store_path),
            "--output",
            str(output),
            "--lookback-hours",
            "1",
        ],
    )

    main()

    store_report = json.loads(
        (store_path / "shadow_gap_incidents.json").read_text(encoding="utf-8")
    )
    assert json.loads(output.read_text(encoding="utf-8")) == store_report
    assert store_report["method"]["history_mutated"] is False
