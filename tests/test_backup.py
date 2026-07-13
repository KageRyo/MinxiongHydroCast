import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.operations.backup import (
    BackupError,
    create_backup,
    prune_backups,
    restore_backup,
    verify_backup,
)
from minxionghydrocast.operations.snapshot_store import DatasetPayload, SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def source_store(tmp_path: Path, now: datetime) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "operations")
    store.publish(
        mode="live",
        started_at=now.isoformat(),
        completed_at=now.isoformat(),
        datasets=[
            DatasetPayload(
                name="rain_gauges",
                product_type="official_observation",
                records=[
                    {
                        "station": "Minxiong",
                        "observed_at": now.isoformat(timespec="seconds"),
                    }
                ],
                fieldnames=["station", "observed_at"],
                health={
                    "state": "healthy",
                    "ready": True,
                    "observed_at": now.isoformat(timespec="seconds"),
                    "age_minutes": 0,
                    "max_age_minutes": 30,
                    "schema_sha256": "fixture",
                    "schema_errors": [],
                },
            )
        ],
        health={
            "state": "healthy",
            "ready": True,
            "datasets": {"rain_gauges": "healthy"},
        },
        now=now,
    )
    return store


def test_backup_restore_drill_preserves_verified_latest_snapshot(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    source = source_store(tmp_path, now)

    archive, metadata = create_backup(source, tmp_path / "backups", now=now)
    verified = verify_backup(archive)
    report = restore_backup(
        archive,
        tmp_path / "restored-operations",
        now=now + timedelta(minutes=1),
    )
    restored = SnapshotStore(tmp_path / "restored-operations")

    assert verified == metadata
    assert report["verified"] is True
    assert report["archive_sha256"] == metadata.archive_sha256
    assert restored.read_latest()["snapshot_id"] == metadata.latest_snapshot_id
    assert restored.verify_snapshot(restored.read_latest()) == []
    assert json.loads((restored.root / "restore_report.json").read_text())["verified"] is True


def test_backup_verification_rejects_tampered_archive(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    archive, _metadata = create_backup(
        source_store(tmp_path, now),
        tmp_path / "backups",
        now=now,
    )
    with archive.open("ab") as handle:
        handle.write(b"tamper")

    with pytest.raises(BackupError, match="size does not match"):
        verify_backup(archive)


def test_restore_refuses_existing_target(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    archive, _metadata = create_backup(
        source_store(tmp_path, now),
        tmp_path / "backups",
        now=now,
    )
    target = tmp_path / "existing"
    target.mkdir()

    with pytest.raises(BackupError, match="already exists"):
        restore_backup(archive, target)


def test_backup_refuses_destination_inside_store(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    store = source_store(tmp_path, now)

    with pytest.raises(BackupError, match="outside the operational store"):
        create_backup(store, store.root / "backups", now=now)


def test_backup_refuses_unsupported_member_types(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    store = source_store(tmp_path, now)
    (store.root / "unexpected-link").symlink_to(store.root / "latest.json")

    with pytest.raises(BackupError, match="member type is not allowed"):
        create_backup(store, tmp_path / "backups", now=now)

    assert list((tmp_path / "backups").iterdir()) == []


def test_backup_retention_removes_verified_expired_pair(tmp_path):
    old = datetime(2026, 7, 1, 10, 0, tzinfo=TAIPEI_TZ)
    archive, _metadata = create_backup(
        source_store(tmp_path, old),
        tmp_path / "backups",
        now=old,
    )

    removed = prune_backups(
        tmp_path / "backups",
        retention_days=5,
        now=old + timedelta(days=6),
    )

    assert removed == [archive.name]
    assert not archive.exists()
    assert not archive.with_suffix(archive.suffix + ".json").exists()
