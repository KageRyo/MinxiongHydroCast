"""Update a rolling radar backtest manifest from the local discovery catalog."""

from __future__ import annotations

import argparse
import fcntl
import time
from datetime import datetime
from pathlib import Path

from minxionghydrocast.io.data_store import (
    DataLayout,
    atomic_write_bytes,
    canonical_json_bytes,
    require_external_data_root,
)
from minxionghydrocast.models.event_evidence_schemas import EventCandidate, EventEvidenceCatalog
from minxionghydrocast.models.rolling_backtest import (
    BacktestEvent,
    BacktestManifest,
    RadarFrame,
    aware_time,
)
from minxionghydrocast.pipelines.backtest_store import backtest_lock
from minxionghydrocast.research.archive_inventory import MetadataIntegrityError, collection_frames
from minxionghydrocast.research.replay_io import contained


def _event(layout: DataLayout, candidate: EventCandidate) -> BacktestEvent:
    radar = candidate.radar_collection
    frames = collection_frames(
        layout, radar.collection, list(radar.frames), candidate.candidate_id, candidate.source_data_id,
    )
    if len(frames) != radar.captured_frame_count or any(frame.sha256 is None for frame in frames):
        raise ValueError(f"catalog and collection frame references differ for {candidate.candidate_id}")
    refs = [RadarFrame.model_validate(frame.model_dump()) for frame in frames]
    start = aware_time(candidate.window_start_time)
    end = aware_time(candidate.window_end_time)
    if any(not start <= aware_time(frame.data_time) <= end for frame in refs):
        raise ValueError(f"frame outside discovery window for {candidate.candidate_id}")
    return BacktestEvent(event_id=candidate.candidate_id, frames=sorted(refs, key=lambda f: f.data_time))


def _check_existing(path: Path, manifest: BacktestManifest) -> None:
    if not path.exists():
        return
    previous = BacktestManifest.model_validate_json(path.read_bytes())
    current = {event.event_id: {frame.data_time: frame for frame in event.frames}
               for event in manifest.events}
    for event in previous.events:
        by_time = current.get(event.event_id, {})
        if any(by_time.get(frame.data_time) != frame for frame in event.frames):
            raise ValueError(f"export would remove or change known frames for {event.event_id}")


def _snapshot(
    layout: DataLayout, since: datetime, until: datetime | None,
) -> tuple[BacktestManifest, dict[str, int]]:
    source = layout.resolve_relative("discovery/event_evidence_catalog.json")
    catalog = EventEvidenceCatalog.model_validate_json(source.read_bytes())
    if Path(catalog.data_root).resolve() != layout.root:
        raise ValueError("discovery catalog data root differs from --root")
    candidates = sorted(catalog.candidates, key=lambda candidate: (
        aware_time(candidate.window_start_time), candidate.candidate_id,
    ))
    events: list[BacktestEvent] = []
    last_end: datetime | None = None
    skipped_overlap = 0
    skipped_empty = 0
    for candidate in candidates:
        trigger = aware_time(candidate.first_trigger_time)
        if trigger < since or (until is not None and trigger >= until):
            continue
        if last_end is not None and aware_time(candidate.window_start_time) <= last_end:
            skipped_overlap += 1
            continue
        last_end = aware_time(candidate.window_end_time)
        if candidate.radar_collection.captured_frame_count == 0:
            skipped_empty += 1
            continue
        events.append(_event(layout, candidate))

    if not events:
        raise ValueError("no non-overlapping discovery events with radar captures in the requested interval")
    manifest = BacktestManifest(schema_version="1.0", events=events)
    counts = {"events": len(events), "frames": sum(len(event.frames) for event in events),
              "skipped_overlap": skipped_overlap, "skipped_empty": skipped_empty}
    return manifest, counts


def _snapshot_after_discovery(
    layout: DataLayout, since: datetime, until: datetime | None,
) -> tuple[BacktestManifest, dict[str, int]]:
    # Discovery replaces collections before publishing the new catalog. A conflicting
    # read retries under a shared lock, while normal exports never block discovery.
    lock_path = layout.resolve_relative(layout.lock_path.relative_to(layout.root).as_posix())
    deadline = time.monotonic() + 30
    with lock_path.open("rb") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError("discovery is still updating the catalog; retry the export") from exc
                time.sleep(0.25)
        return _snapshot(layout, since, until)


def export_discovery_manifest(
    *, root: Path, since: datetime, until: datetime | None, output_path: Path,
) -> dict[str, int]:
    """Export new frames while preserving the identity of every previously exported frame."""
    since = aware_time(since)
    until = aware_time(until) if until is not None else None
    if until is not None and until <= since:
        raise ValueError("--until must be later than --since")
    layout = DataLayout(root)
    require_external_data_root(layout, repository_root=Path(__file__).resolve().parents[3])
    output = contained(layout, output_path)
    if not output.is_relative_to(layout.root / "backtests" / "inputs") or output.suffix != ".json":
        raise ValueError("--output must be a JSON file inside <root>/backtests/inputs")

    layout.resolve_relative("backtests/.lock")
    with backtest_lock(layout.resolve_relative("backtests")):
        try:
            manifest, counts = _snapshot(layout, since, until)
        except MetadataIntegrityError:
            if not layout.lock_path.is_file():
                raise
            manifest, counts = _snapshot_after_discovery(layout, since, until)
        _check_existing(output, manifest)
        raw = canonical_json_bytes(manifest.model_dump(mode="json"))
        if not output.is_file() or output.read_bytes() != raw:
            atomic_write_bytes(output, raw)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--since", type=aware_time, required=True, help="Include first triggers at or after this time.")
    parser.add_argument("--until", type=aware_time, help="Exclude first triggers at or after this time.")
    parser.add_argument("--output", type=Path, required=True, help="JSON file under <root>/backtests/inputs.")
    args = parser.parse_args()
    try:
        counts = export_discovery_manifest(
            root=args.root, since=args.since, until=args.until, output_path=args.output,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print("[OK] backtest manifest: " + ", ".join(f"{name}={count}" for name, count in counts.items()))
