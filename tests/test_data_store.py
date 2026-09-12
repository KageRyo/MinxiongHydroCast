import json
import os

import pytest

from minxionghydrocast.io.data_store import DataLayout, DataLockError


def test_event_discovery_lock_rejects_overlapping_processes(tmp_path):
    first = DataLayout(tmp_path)
    second = DataLayout(tmp_path)

    with first.event_discovery_lock():
        payload = json.loads(first.lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["active"] is True
        with pytest.raises(DataLockError, match="event discovery already running"):
            with second.event_discovery_lock():
                pass

    released = json.loads(first.lock_path.read_text(encoding="utf-8"))
    assert released["active"] is False
    assert "released_at" in released


def test_event_discovery_lock_ignores_stale_metadata(tmp_path):
    layout = DataLayout(tmp_path)
    layout.ensure()
    layout.lock_path.write_text(
        json.dumps(
            {
                "pid": 99_999_999,
                "acquired_at": "2026-07-11T10:00:00+08:00",
                "active": True,
            }
        ),
        encoding="utf-8",
    )

    with layout.event_discovery_lock():
        payload = json.loads(layout.lock_path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid()
        assert payload["active"] is True
