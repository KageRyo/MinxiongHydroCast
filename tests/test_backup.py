import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.operations.backup import (
    BackupError,
    create_backup,
    prune_backups,
    restore_backup,
    verify_backup,
)
from minxionghydrocast.operations.snapshot_store import (
    DatasetPayload,
    RunLockError,
    SnapshotStore,
)

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


def test_backup_retries_transient_collection_lock(tmp_path, monkeypatch):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    store = source_store(tmp_path, now)
    real_collection_lock = store.collection_lock
    lock_attempts = 0
    sleep_delays: list[float] = []

    @contextmanager
    def flaky_collection_lock() -> Iterator[None]:
        nonlocal lock_attempts
        lock_attempts += 1
        if lock_attempts < 3:
            raise RunLockError("collection already running")
        with real_collection_lock():
            yield

    monkeypatch.setattr(store, "collection_lock", flaky_collection_lock)

    archive, metadata = create_backup(
        store,
        tmp_path / "backups",
        now=now,
        lock_retry_attempts=4,
        lock_retry_backoff_seconds=2,
        sleep=sleep_delays.append,
    )

    assert archive.is_file()
    assert metadata.snapshot_count == 1
    assert lock_attempts == 3
    assert sleep_delays == [2, 4]


def test_backup_fails_after_bounded_collection_lock_retries(tmp_path, monkeypatch):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    store = source_store(tmp_path, now)
    lock_attempts = 0
    sleep_delays: list[float] = []

    @contextmanager
    def locked_collection() -> Iterator[None]:
        nonlocal lock_attempts
        lock_attempts += 1
        raise RunLockError("collection already running")
        yield

    monkeypatch.setattr(store, "collection_lock", locked_collection)

    with pytest.raises(RunLockError, match="collection already running"):
        create_backup(
            store,
            tmp_path / "backups",
            now=now,
            lock_retry_attempts=3,
            lock_retry_backoff_seconds=2,
            sleep=sleep_delays.append,
        )

    assert lock_attempts == 3
    assert sleep_delays == [2, 4]
    assert list((tmp_path / "backups").iterdir()) == []


@pytest.mark.parametrize(
    ("attempts", "backoff", "message"),
    [
        (0, 1, "attempts must be at least one"),
        (1, -1, "backoff seconds cannot be negative"),
    ],
)
def test_backup_rejects_invalid_lock_retry_configuration(
    tmp_path, attempts, backoff, message
):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)

    with pytest.raises(BackupError, match=message):
        create_backup(
            source_store(tmp_path, now),
            tmp_path / "backups",
            now=now,
            lock_retry_attempts=attempts,
            lock_retry_backoff_seconds=backoff,
            sleep=lambda _delay: None,
        )


def test_backup_refuses_unsupported_member_types(tmp_path):
    now = datetime(2026, 7, 12, 10, 0, tzinfo=TAIPEI_TZ)
    store = source_store(tmp_path, now)
    (store.root / "unexpected-link").symlink_to(store.root / "latest.json")

    with pytest.raises(BackupError, match="member type is not allowed"):
        create_backup(
            store,
            tmp_path / "backups",
            now=now,
            sleep=lambda _delay: pytest.fail("non-lock errors must not be retried"),
        )

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
