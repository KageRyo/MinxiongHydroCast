"""Durable, checksummed storage primitives for external research artifacts."""

from __future__ import annotations

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


class ResearchLockError(RuntimeError):
    """Raised when another research collection process owns the lock."""


class ResearchLayout:
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
    def event_discovery_lock(self) -> Iterator[None]:
        self.ensure()
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
                raise ResearchLockError(
                    f"event discovery already running: {self.lock_path}"
                ) from exc
        try:
            payload = {
                "pid": os.getpid(),
                "acquired_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
            }
            os.write(descriptor, canonical_json_bytes(payload))
            os.fsync(descriptor)
            os.close(descriptor)
            yield
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass
            self.lock_path.unlink(missing_ok=True)


def require_external_research_root(layout: ResearchLayout, *, repository_root: Path) -> None:
    repository_root = repository_root.resolve()
    try:
        layout.root.relative_to(repository_root)
    except ValueError:
        return
    raise ValueError("research root must be outside the Git repository")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_record(layout: ResearchLayout, path: Path, *, kind: str) -> ArtifactRecord:
    return ArtifactRecord(
        kind=kind,
        path=layout.relative(path),
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
    )


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
