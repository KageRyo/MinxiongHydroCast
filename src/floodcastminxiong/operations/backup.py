"""Checksummed backup and restore tooling for the operational snapshot store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tarfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from floodcastminxiong.operations.collector import DEFAULT_STORE
from floodcastminxiong.operations.snapshot_store import SnapshotStore, SnapshotStoreError

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
BACKUP_SCHEMA_VERSION = 1


class BackupError(RuntimeError):
    """Raised when a backup or restore cannot be proven valid."""


class BackupMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: int = Field(ge=1, le=BACKUP_SCHEMA_VERSION)
    archive: str
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    archive_size_bytes: int = Field(ge=1)
    created_at: str
    source_store: str
    latest_snapshot_id: str
    snapshot_count: int = Field(ge=1)
    file_count: int = Field(ge=1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _verify_store(store: SnapshotStore) -> tuple[dict[str, Any], int]:
    latest = store.read_latest()
    if latest is None:
        raise BackupError("operational store has no latest successful snapshot")
    manifests, scan_errors = store.scan_manifests()
    errors = list(scan_errors)
    for manifest in manifests:
        errors.extend(
            f"{manifest.get('snapshot_id', 'unknown')}: {error}"
            for error in store.verify_snapshot(manifest)
        )
    if errors:
        raise BackupError("operational store verification failed: " + "; ".join(errors))
    return latest, len(manifests)


def _tar_filter(info: tarfile.TarInfo) -> tarfile.TarInfo | None:
    path = PurePosixPath(info.name)
    if path.name == ".collector.lock" or any(
        part.startswith(".snapshot-") and part.endswith(".tmp") for part in path.parts
    ):
        return None
    return info


def create_backup(
    store: SnapshotStore,
    backup_dir: Path,
    *,
    now: datetime | None = None,
) -> tuple[Path, BackupMetadata]:
    now = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    source_root = store.root.resolve()
    destination = backup_dir.resolve()
    if destination == source_root or destination.is_relative_to(source_root):
        raise BackupError("backup directory must be outside the operational store")
    destination.mkdir(parents=True, exist_ok=True)
    timestamp = now.strftime("%Y%m%dT%H%M%S%z")
    archive = destination / f"floodcast-minxiong-{timestamp}.tar.gz"
    temporary = destination / f".{archive.name}.{uuid.uuid4().hex}.tmp"
    if archive.exists() or archive.with_suffix(archive.suffix + ".json").exists():
        raise BackupError(f"backup already exists: {archive}")

    try:
        with store.collection_lock():
            latest, snapshot_count = _verify_store(store)
            with tarfile.open(temporary, mode="w:gz") as bundle:
                bundle.add(source_root, arcname="operations", filter=_tar_filter)
        with tarfile.open(temporary, mode="r:gz") as bundle:
            members = _validated_members(bundle)
            file_count = sum(member.isfile() for member in members)
        os.replace(temporary, archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    metadata = BackupMetadata(
        schema_version=BACKUP_SCHEMA_VERSION,
        archive=archive.name,
        archive_sha256=_sha256(archive),
        archive_size_bytes=archive.stat().st_size,
        created_at=now.isoformat(timespec="seconds"),
        source_store=str(source_root),
        latest_snapshot_id=str(latest["snapshot_id"]),
        snapshot_count=snapshot_count,
        file_count=file_count,
    )
    _atomic_json(
        archive.with_suffix(archive.suffix + ".json"),
        metadata.model_dump(),
    )
    return archive, metadata


def read_backup_metadata(archive: Path) -> BackupMetadata:
    sidecar = archive.with_suffix(archive.suffix + ".json")
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        metadata = BackupMetadata.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        raise BackupError(f"invalid backup metadata: {sidecar}") from exc
    if metadata.archive != archive.name:
        raise BackupError("backup metadata archive name does not match")
    if not archive.is_file():
        raise BackupError(f"backup archive is missing: {archive}")
    if archive.stat().st_size != metadata.archive_size_bytes:
        raise BackupError("backup archive size does not match metadata")
    if _sha256(archive) != metadata.archive_sha256:
        raise BackupError("backup archive checksum does not match metadata")
    return metadata


def _validated_members(bundle: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members = bundle.getmembers()
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts:
            raise BackupError(f"unsafe backup member path: {member.name}")
        if not path.parts or path.parts[0] != "operations":
            raise BackupError(f"backup member is outside operations root: {member.name}")
        if not (member.isdir() or member.isfile()):
            raise BackupError(f"backup member type is not allowed: {member.name}")
    return members


def verify_backup(archive: Path) -> BackupMetadata:
    metadata = read_backup_metadata(archive)
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = _validated_members(bundle)
    except (OSError, tarfile.TarError) as exc:
        raise BackupError(f"backup archive cannot be read: {archive}") from exc
    if sum(member.isfile() for member in members) != metadata.file_count:
        raise BackupError("backup file count does not match metadata")
    return metadata


def _extract_files(bundle: tarfile.TarFile, members: list[tarfile.TarInfo], root: Path) -> None:
    for member in members:
        relative = Path(*PurePosixPath(member.name).parts)
        destination = root / relative
        if member.isdir():
            destination.mkdir(parents=True, exist_ok=True)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        source = bundle.extractfile(member)
        if source is None:
            raise BackupError(f"backup member cannot be extracted: {member.name}")
        with source, destination.open("wb") as output:
            shutil.copyfileobj(source, output)
        os.chmod(destination, member.mode & 0o700)


def restore_backup(
    archive: Path,
    target: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    metadata = verify_backup(archive)
    target = target.resolve()
    if target.exists():
        raise BackupError(f"restore target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.restore-{uuid.uuid4().hex}"
    staging.mkdir()
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = _validated_members(bundle)
            _extract_files(bundle, members, staging)
        restored_root = staging / "operations"
        restored_store = SnapshotStore(restored_root)
        latest, snapshot_count = _verify_store(restored_store)
        if str(latest["snapshot_id"]) != metadata.latest_snapshot_id:
            raise BackupError("restored latest snapshot does not match backup metadata")
        if snapshot_count != metadata.snapshot_count:
            raise BackupError("restored snapshot count does not match backup metadata")
        os.replace(restored_root, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    shutil.rmtree(staging, ignore_errors=True)
    completed_at = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    report = {
        "schema_version": 1,
        "restored_at": completed_at.isoformat(timespec="seconds"),
        "archive": str(archive.resolve()),
        "archive_sha256": metadata.archive_sha256,
        "target": str(target),
        "latest_snapshot_id": metadata.latest_snapshot_id,
        "snapshot_count": metadata.snapshot_count,
        "verified": True,
    }
    _atomic_json(target / "restore_report.json", report)
    return report


def prune_backups(
    backup_dir: Path, *, retention_days: int, now: datetime | None = None
) -> list[str]:
    if retention_days < 1:
        raise ValueError("backup retention_days must be at least one")
    now = (now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
    cutoff = now - timedelta(days=retention_days)
    removed: list[str] = []
    for sidecar in backup_dir.glob("floodcast-minxiong-*.tar.gz.json"):
        archive = sidecar.with_suffix("")
        try:
            metadata = read_backup_metadata(archive)
            created_at = datetime.fromisoformat(metadata.created_at).astimezone(TAIPEI_TZ)
        except (BackupError, ValueError):
            continue
        if created_at < cutoff:
            archive.unlink(missing_ok=True)
            sidecar.unlink(missing_ok=True)
            removed.append(archive.name)
    return sorted(removed)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Back up or restore the operational snapshot store."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("create")
    backup_parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    backup_parser.add_argument("--backup-dir", type=Path, required=True)
    backup_parser.add_argument("--retention-days", type=int, default=30)

    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("--archive", type=Path, required=True)

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--archive", type=Path, required=True)
    restore_parser.add_argument("--target", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            archive, metadata = create_backup(
                SnapshotStore(args.store),
                args.backup_dir,
            )
            removed = prune_backups(
                args.backup_dir,
                retention_days=args.retention_days,
            )
            print(
                f"[OK] Backup {archive} snapshots={metadata.snapshot_count} "
                f"sha256={metadata.archive_sha256} pruned={len(removed)}"
            )
        elif args.command == "verify":
            metadata = verify_backup(args.archive)
            print(
                f"[OK] Backup verified snapshots={metadata.snapshot_count} "
                f"sha256={metadata.archive_sha256}"
            )
        else:
            report = restore_backup(args.archive, args.target)
            print(
                f"[OK] Restore verified target={report['target']} "
                f"snapshot={report['latest_snapshot_id']}"
            )
    except (BackupError, SnapshotStoreError, OSError) as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
