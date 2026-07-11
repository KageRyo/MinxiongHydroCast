"""Immutable, versioned storage for operational observation snapshots."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

from floodcastminxiong.operations.health import schema_fingerprint

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


class RunLockError(RuntimeError):
    """Raised when another collection process owns the store lock."""


class SnapshotStoreError(RuntimeError):
    """Raised when persisted snapshot metadata is missing or corrupt."""


@dataclass(frozen=True)
class DatasetPayload:
    name: str
    product_type: str
    records: list[dict[str, object]]
    fieldnames: list[str]
    health: dict[str, Any]


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes_durable(path: Path, payload: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


class SnapshotStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.snapshots_dir = root / "snapshots"
        self.latest_path = root / "latest.json"
        self.latest_attempt_path = root / "latest_attempt.json"
        self.lock_path = root / ".collector.lock"

    def initialize(self) -> None:
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)

    def _remove_stale_lock(self) -> bool:
        try:
            payload = json.loads(self.lock_path.read_text(encoding="utf-8"))
            pid = int(payload["pid"])
        except FileNotFoundError:
            return True
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            try:
                lock_age_seconds = max(0.0, time.time() - self.lock_path.stat().st_mtime)
            except FileNotFoundError:
                return True
            if lock_age_seconds <= 60:
                return False
            self.lock_path.unlink(missing_ok=True)
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            self.lock_path.unlink(missing_ok=True)
            return True
        except PermissionError:
            return False
        return False

    @contextmanager
    def collection_lock(self) -> Iterator[None]:
        self.initialize()
        while True:
            try:
                descriptor = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
                break
            except FileExistsError as exc:
                if self._remove_stale_lock():
                    continue
                raise RunLockError(f"collection already running: {self.lock_path}") from exc
        try:
            payload = {
                "pid": os.getpid(),
                "acquired_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
            }
            os.write(descriptor, _json_bytes(payload))
            os.fsync(descriptor)
            os.close(descriptor)
            yield
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            self.lock_path.unlink(missing_ok=True)

    def _snapshot_id(self, now: datetime) -> str:
        timestamp = now.astimezone(TAIPEI_TZ).strftime("%Y%m%dT%H%M%S%f%z")
        return f"{timestamp}-{uuid.uuid4().hex[:8]}"

    def _atomic_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        _write_bytes_durable(temporary, _json_bytes(payload))
        os.replace(temporary, path)
        _fsync_directory(path.parent)

    def _write_pointer(self, path: Path, manifest: dict[str, Any]) -> None:
        manifest_path = self.snapshots_dir / str(manifest["snapshot_id"]) / "manifest.json"
        self._atomic_json(
            path,
            {
                "snapshot_id": manifest["snapshot_id"],
                "manifest": f"snapshots/{manifest['snapshot_id']}/manifest.json",
                "manifest_sha256": _sha256(manifest_path),
                "status": manifest["status"],
                "updated_at": manifest["completed_at"],
            },
        )

    def publish(
        self,
        *,
        mode: str,
        started_at: str,
        completed_at: str,
        datasets: list[DatasetPayload],
        health: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        now = now or datetime.now(TAIPEI_TZ)
        snapshot_id = self._snapshot_id(now)
        staging = self.root / f".snapshot-{snapshot_id}.tmp"
        final = self.snapshots_dir / snapshot_id
        staging.mkdir(parents=True)
        dataset_dir = staging / "datasets"
        dataset_dir.mkdir()
        manifest_datasets: dict[str, Any] = {}
        try:
            for dataset in datasets:
                relative_path = Path("datasets") / f"{dataset.name}.csv"
                output_path = staging / relative_path
                with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
                    writer = csv.DictWriter(handle, fieldnames=dataset.fieldnames)
                    writer.writeheader()
                    writer.writerows(dataset.records)
                    handle.flush()
                    os.fsync(handle.fileno())
                manifest_datasets[dataset.name] = {
                    "product_type": dataset.product_type,
                    "path": relative_path.as_posix(),
                    "row_count": len(dataset.records),
                    "fields": dataset.fieldnames,
                    "schema_sha256": schema_fingerprint(dataset.fieldnames),
                    "sha256": _sha256(output_path),
                    "health": dataset.health,
                }

            manifest = {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "status": "ok",
                "mode": mode,
                "started_at": started_at,
                "completed_at": completed_at,
                "health": health,
                "datasets": manifest_datasets,
                "metadata": metadata or {},
            }
            _write_bytes_durable(staging / "manifest.json", _json_bytes(manifest))
            _fsync_directory(dataset_dir)
            _fsync_directory(staging)
            os.replace(staging, final)
            _fsync_directory(self.snapshots_dir)
            self._write_pointer(self.latest_attempt_path, manifest)
            self._write_pointer(self.latest_path, manifest)
            return manifest
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise

    def publish_failure(
        self,
        *,
        mode: str,
        started_at: str,
        completed_at: str,
        failure_reason: str,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        now = now or datetime.now(TAIPEI_TZ)
        snapshot_id = self._snapshot_id(now)
        final = self.snapshots_dir / snapshot_id
        final.mkdir()
        manifest = {
            "schema_version": 1,
            "snapshot_id": snapshot_id,
            "status": "error",
            "mode": mode,
            "started_at": started_at,
            "completed_at": completed_at,
            "failure_reason": failure_reason,
            "health": {"state": "collector_error", "ready": False, "datasets": {}},
            "datasets": {},
            "metadata": metadata or {},
        }
        _write_bytes_durable(final / "manifest.json", _json_bytes(manifest))
        _fsync_directory(final)
        _fsync_directory(self.snapshots_dir)
        self._write_pointer(self.latest_attempt_path, manifest)
        return manifest

    def _read_pointer(self, path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        try:
            pointer = json.loads(path.read_text(encoding="utf-8"))
            manifest_path = (self.root / str(pointer["manifest"])).resolve()
            expected_manifest_sha256 = str(pointer["manifest_sha256"])
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise SnapshotStoreError(f"invalid snapshot pointer: {path}") from exc
        if not manifest_path.is_relative_to(self.snapshots_dir.resolve()):
            raise SnapshotStoreError(
                f"snapshot manifest is outside snapshots directory: {manifest_path}"
            )
        if not manifest_path.exists():
            raise SnapshotStoreError(f"snapshot manifest is missing: {manifest_path}")
        try:
            actual_manifest_sha256 = _sha256(manifest_path)
        except OSError as exc:
            raise SnapshotStoreError(f"snapshot manifest cannot be read: {manifest_path}") from exc
        if actual_manifest_sha256 != expected_manifest_sha256:
            raise SnapshotStoreError(f"snapshot manifest checksum mismatch: {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SnapshotStoreError(f"invalid snapshot manifest: {manifest_path}") from exc
        if not isinstance(manifest, dict):
            raise SnapshotStoreError(f"snapshot manifest must be an object: {manifest_path}")
        return manifest

    def read_latest(self) -> dict[str, Any] | None:
        return self._read_pointer(self.latest_path)

    def read_latest_attempt(self) -> dict[str, Any] | None:
        return self._read_pointer(self.latest_attempt_path)

    def _dataset_path(self, manifest: dict[str, Any], details: dict[str, Any]) -> Path:
        snapshot_root = (self.snapshots_dir / str(manifest["snapshot_id"])).resolve()
        path = (snapshot_root / str(details["path"])).resolve()
        if not path.is_relative_to(snapshot_root):
            raise SnapshotStoreError(f"dataset path escapes snapshot root: {path}")
        return path

    def verify_snapshot(self, manifest: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        required_manifest_fields = {
            "snapshot_id",
            "status",
            "mode",
            "completed_at",
            "datasets",
        }
        missing_manifest_fields = sorted(required_manifest_fields - set(manifest))
        if missing_manifest_fields:
            return [f"manifest missing fields: {', '.join(missing_manifest_fields)}"]
        datasets = manifest.get("datasets")
        if not isinstance(datasets, dict):
            return ["manifest datasets must be an object"]
        for name, raw_details in sorted(datasets.items()):
            if not isinstance(raw_details, dict):
                errors.append(f"{name}: dataset metadata must be an object")
                continue
            try:
                path = self._dataset_path(manifest, raw_details)
                expected_sha256 = str(raw_details["sha256"])
                fields = list(raw_details["fields"])
                expected_schema = str(raw_details["schema_sha256"])
            except (KeyError, TypeError, SnapshotStoreError) as exc:
                errors.append(f"{name}: invalid dataset metadata: {exc}")
                continue
            if not path.is_file():
                errors.append(f"{name}: dataset file is missing")
                continue
            try:
                actual_sha256 = _sha256(path)
            except OSError as exc:
                errors.append(f"{name}: dataset cannot be read: {exc}")
                continue
            if actual_sha256 != expected_sha256:
                errors.append(f"{name}: dataset checksum mismatch")
            if schema_fingerprint(fields) != expected_schema:
                errors.append(f"{name}: schema checksum mismatch")
            try:
                with path.open(newline="", encoding="utf-8-sig") as handle:
                    actual_fields = next(csv.reader(handle), [])
            except (OSError, UnicodeError) as exc:
                errors.append(f"{name}: dataset cannot be read: {exc}")
                continue
            if actual_fields != fields:
                errors.append(f"{name}: CSV header does not match manifest fields")
        return errors

    def read_dataset(self, manifest: dict[str, Any], name: str) -> list[dict[str, str]]:
        datasets = manifest.get("datasets")
        if not isinstance(datasets, dict):
            raise SnapshotStoreError("manifest datasets must be an object")
        details = datasets.get(name)
        if not isinstance(details, dict):
            raise KeyError(name)
        path = self._dataset_path(manifest, details)
        errors = self.verify_snapshot(
            {
                **manifest,
                "datasets": {name: details},
            }
        )
        if errors:
            raise SnapshotStoreError("; ".join(errors))
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return list(csv.DictReader(handle))

    def prune(self, *, retention_days: int, now: datetime | None = None) -> list[str]:
        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")
        self.initialize()
        now = now or datetime.now(TAIPEI_TZ)
        cutoff = now - timedelta(days=retention_days)
        protected = {
            manifest["snapshot_id"]
            for manifest in (self.read_latest(), self.read_latest_attempt())
            if manifest is not None
        }
        removed: list[str] = []
        for directory in self.snapshots_dir.iterdir():
            if not directory.is_dir() or directory.name in protected:
                continue
            manifest_path = directory / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            try:
                completed_at = datetime.fromisoformat(str(manifest["completed_at"]))
            except (KeyError, ValueError):
                continue
            if completed_at < cutoff:
                shutil.rmtree(directory)
                removed.append(directory.name)
        if removed:
            _fsync_directory(self.snapshots_dir)
        return sorted(removed)
