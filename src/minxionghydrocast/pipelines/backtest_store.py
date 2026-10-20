"""Atomic research records and a kernel-backed rolling-backtest lock."""

import fcntl
import hashlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from minxionghydrocast.io.data_store import atomic_write_bytes, canonical_json_bytes


def digest(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def save_record(path: Path, record: dict[str, Any]) -> None:
    envelope = {"sha256": digest(record), "record": record}
    atomic_write_bytes(path, canonical_json_bytes(envelope))


def load_record(path: Path) -> dict[str, Any]:
    try:
        envelope = json.loads(path.read_text())
        record = envelope["record"]
        if not isinstance(record, dict) or digest(record) != envelope["sha256"]:
            raise ValueError("checksum mismatch")
        return record
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"backtest record integrity failure: {path.name}") from exc


@contextmanager
def backtest_lock(directory: Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".lock").open("a+b") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("rolling backtest already running") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
