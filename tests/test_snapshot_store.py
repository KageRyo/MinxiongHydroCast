import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from floodcastminxiong.operations.snapshot_store import (
    DatasetPayload,
    RunLockError,
    SnapshotStore,
    SnapshotStoreError,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def dataset() -> DatasetPayload:
    return DatasetPayload(
        name="rain_gauges",
        product_type="official_observation",
        records=[{"station": "Minxiong", "observed_at": "2026-07-11T10:00:00+08:00"}],
        fieldnames=["station", "observed_at"],
        health={
            "state": "healthy",
            "ready": True,
            "observed_at": "2026-07-11T10:00:00+08:00",
            "age_minutes": 0,
            "max_age_minutes": 30,
            "schema_sha256": "fixture",
            "schema_errors": [],
        },
    )


def publish(store: SnapshotStore, now: datetime) -> dict[str, object]:
    return store.publish(
        mode="live",
        started_at=now.isoformat(),
        completed_at=now.isoformat(),
        datasets=[dataset()],
        health={
            "state": "healthy",
            "ready": True,
            "datasets": {"rain_gauges": "healthy"},
        },
        now=now,
    )


def test_snapshot_store_publishes_immutable_dataset_and_latest_pointer(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)

    manifest = publish(store, now)

    assert store.read_latest()["snapshot_id"] == manifest["snapshot_id"]
    assert store.read_latest_attempt()["status"] == "ok"
    assert store.read_dataset(manifest, "rain_gauges") == [
        {"station": "Minxiong", "observed_at": "2026-07-11T10:00:00+08:00"}
    ]
    details = manifest["datasets"]["rain_gauges"]
    assert len(details["sha256"]) == 64
    assert len(details["schema_sha256"]) == 64
    assert store.verify_snapshot(manifest) == []


def test_snapshot_store_rejects_tampered_dataset(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    manifest = publish(store, now)
    details = manifest["datasets"]["rain_gauges"]
    dataset_path = (
        store.snapshots_dir / manifest["snapshot_id"] / details["path"]
    )
    dataset_path.write_text("corrupt\n", encoding="utf-8")

    assert store.verify_snapshot(manifest) == [
        "rain_gauges: dataset checksum mismatch",
        "rain_gauges: CSV header does not match manifest fields",
    ]
    with pytest.raises(SnapshotStoreError, match="dataset checksum mismatch"):
        store.read_dataset(manifest, "rain_gauges")


def test_failed_attempt_does_not_replace_latest_readable_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    latest = publish(store, now)

    failed = store.publish_failure(
        mode="live",
        started_at=(now + timedelta(minutes=10)).isoformat(),
        completed_at=(now + timedelta(minutes=10)).isoformat(),
        failure_reason="source unavailable",
        now=now + timedelta(minutes=10),
    )

    assert store.read_latest()["snapshot_id"] == latest["snapshot_id"]
    assert store.read_latest_attempt()["snapshot_id"] == failed["snapshot_id"]
    assert store.read_latest_attempt()["status"] == "error"


def test_snapshot_store_rejects_manifest_outside_snapshot_directory(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    store.initialize()
    outside = tmp_path / "outside.json"
    outside.write_text("{}\n", encoding="utf-8")
    store.latest_path.write_text(
        json.dumps(
            {
                "manifest": "../../outside.json",
                "manifest_sha256": "not-used",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        SnapshotStoreError,
        match="snapshot manifest is outside snapshots directory",
    ):
        store.read_latest()


def test_snapshot_store_round_trips_atomic_report(tmp_path):
    store = SnapshotStore(tmp_path / "operations")

    path = store.write_report("shadow_report.json", {"shadow_gate_passed": False})

    assert path == store.root / "shadow_report.json"
    assert store.read_report("shadow_report.json") == {"shadow_gate_passed": False}


def test_collection_lock_rejects_overlapping_process(tmp_path):
    store = SnapshotStore(tmp_path / "operations")

    with store.collection_lock():
        with pytest.raises(RunLockError, match="collection already running"):
            with store.collection_lock():
                pass


def test_collection_lock_recovers_after_process_dies(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    store.initialize()
    store.lock_path.write_text(
        json.dumps({"pid": 99_999_999, "acquired_at": "2026-07-11T10:00:00+08:00"}),
        encoding="utf-8",
    )

    with store.collection_lock():
        lock = json.loads(store.lock_path.read_text(encoding="utf-8"))
        assert lock["pid"] == os.getpid()

    assert not store.lock_path.exists()


def test_collection_lock_does_not_delete_new_partial_lock(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    store.initialize()
    store.lock_path.write_text("", encoding="utf-8")

    with pytest.raises(RunLockError, match="collection already running"):
        with store.collection_lock():
            pass

    assert store.lock_path.exists()


def test_prune_removes_expired_unreferenced_snapshots(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    old = datetime(2026, 7, 1, 10, 0, tzinfo=TAIPEI_TZ)
    recent = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    old_manifest = publish(store, old)
    recent_manifest = publish(store, recent)

    removed = store.prune(retention_days=5, now=recent)

    assert removed == [old_manifest["snapshot_id"]]
    assert store.read_latest()["snapshot_id"] == recent_manifest["snapshot_id"]
