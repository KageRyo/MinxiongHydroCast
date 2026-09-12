"""Durable, checksummed storage primitives for external data artifacts."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from minxionghydrocast.models.dataset_schemas import ArtifactRecord

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


class DataLockError(RuntimeError):
    """Raised when another research collection process owns the lock."""


class DataLayout:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.raw = self.root / "raw"
        self.events = self.root / "events"
        self.tensors = self.root / "tensors"
        self.models = self.root / "models"
        self.reports = self.root / "reports"
        self.catalog = self.root / "catalog"
        self.discovery = self.root / "discovery"
        self.discovery_history = self.discovery / "history"
        self.discovery_cache = self.discovery / "scan_cache"
        self.discovery_metrics = self.discovery / "frame_metrics"
        self.evidence = self.root / "evidence"
        self.lock_path = self.discovery / ".event-discover.lock"

    def ensure(self) -> None:
        for path in (
            self.root,
            self.raw,
            self.events,
            self.tensors,
            self.models,
            self.reports,
            self.catalog,
            self.discovery,
            self.discovery_history,
            self.discovery_cache,
            self.discovery_metrics,
            self.evidence,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def resolve_relative(self, relative_path: str) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            raise ValueError(f"research artifact path must be relative: {relative_path}")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"research artifact escapes root: {relative_path}") from exc
        return resolved

    @contextmanager
    def event_discovery_lock(self) -> Iterator[None]:
        """Serialize discovery and review across processes and PID namespaces.

        The lock file is intentionally persistent and the kernel advisory lock is
        the source of truth.  PID-based stale-lock recovery is unsafe when the
        writer and reviewer run in different PID namespaces (for example, a
        systemd service and a sandbox), because a live PID can look absent.
        ``flock`` is released by the kernel if a process exits, so no stale-lock
        deletion is needed.
        """
        self.ensure()
        descriptor = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        acquired = False
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DataLockError(
                    f"event discovery already running: {self.lock_path}"
                ) from exc
            acquired = True
            payload = {
                "pid": os.getpid(),
                "acquired_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
                "active": True,
            }
            os.ftruncate(descriptor, 0)
            os.lseek(descriptor, 0, os.SEEK_SET)
            os.write(descriptor, canonical_json_bytes(payload))
            os.fsync(descriptor)
            yield
        finally:
            if acquired:
                try:
                    released_payload = {
                        "pid": os.getpid(),
                        "acquired_at": payload["acquired_at"],
                        "released_at": datetime.now(TAIPEI_TZ).isoformat(
                            timespec="seconds"
                        ),
                        "active": False,
                    }
                    os.ftruncate(descriptor, 0)
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    os.write(descriptor, canonical_json_bytes(released_payload))
                    os.fsync(descriptor)
                finally:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def require_external_data_root(layout: DataLayout, *, repository_root: Path) -> None:
    repository_root = repository_root.resolve()
    try:
        layout.root.relative_to(repository_root)
    except ValueError:
        return
    raise ValueError("data root must be outside the Git repository")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(layout: DataLayout, path: Path, *, kind: str) -> ArtifactRecord:
    return ArtifactRecord(
        kind=kind,
        path=layout.relative(path),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
    )


# These aliases preserve direct-import compatibility for integrations and existing artifacts.
# New code must use DataLayout and require_external_data_root.
ResearchLockError = DataLockError
ResearchLayout = DataLayout
require_external_research_root = require_external_data_root


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_schema(path: Path, payload: BaseModel) -> None:
    atomic_write_bytes(path, canonical_json_bytes(payload.model_dump(mode="json")))


def write_schema_if_changed(path: Path, payload: BaseModel) -> bool:
    serialized = canonical_json_bytes(payload.model_dump(mode="json"))
    if path.is_file() and path.read_bytes() == serialized:
        return False
    atomic_write_bytes(path, serialized)
    return True


def prune_cache(
    root: Path,
    *,
    max_age_seconds: float,
    max_bytes: int,
    now_timestamp: float | None = None,
) -> tuple[int, int]:
    """Remove old cache files first, then oldest files until the byte cap is met."""

    if max_age_seconds < 0 or max_bytes < 0:
        raise ValueError("cache retention limits must not be negative")
    if not root.exists():
        return 0, 0
    now = time.time() if now_timestamp is None else now_timestamp
    removed_files = 0
    removed_bytes = 0
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    remaining: list[Path] = []
    for path in files:
        size = path.stat().st_size
        if now - path.stat().st_mtime > max_age_seconds:
            path.unlink(missing_ok=True)
            removed_files += 1
            removed_bytes += size
        else:
            remaining.append(path)
    total_bytes = sum(path.stat().st_size for path in remaining if path.exists())
    for path in remaining:
        if total_bytes <= max_bytes:
            break
        if not path.exists():
            continue
        size = path.stat().st_size
        path.unlink()
        total_bytes -= size
        removed_files += 1
        removed_bytes += size
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            pass
    return removed_files, removed_bytes
