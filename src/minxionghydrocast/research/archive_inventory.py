"""Normalize existing collection catalogs without changing their data or source contracts."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from minxionghydrocast.ingestion.cwa_event_collector import CwaEventCollection
from minxionghydrocast.io.data_store import DataLayout, sha256_file
from minxionghydrocast.models.archive_coverage import ArchiveInventory, CoverageEntry, CoverageFrame, SourceAttempt
from minxionghydrocast.models.dataset_schemas import ArtifactRecord, DatasetCatalog, RadarDatasetManifest
from minxionghydrocast.models.event_evidence_schemas import EventEvidenceCatalog
from minxionghydrocast.research.replay_io import FAILURES, contained

INVENTORY_ERROR = 'archive inventory unavailable or invalid'


@dataclass
class LoadedInventory:
    entries: list[tuple[CoverageEntry, str]]
    input_sha256: str
    omitted_entries: int
    kind: str


def _metadata(layout: DataLayout, artifact: ArtifactRecord) -> bytes:
    path = layout.resolve_relative(artifact.path)
    if path.stat().st_size != artifact.bytes or sha256_file(path) != artifact.sha256:
        raise ValueError('metadata integrity failure')
    return path.read_bytes()


def _frames(layout: DataLayout, collection_ref: ArtifactRecord | None,
            artifacts: list[ArtifactRecord], event_id: str, data_id: str) -> list[CoverageFrame]:
    if collection_ref is None:
        raise ValueError('collection missing')
    collection = CwaEventCollection.model_validate_json(_metadata(layout, collection_ref))
    if collection.event_id != event_id or collection.data_id != data_id:
        raise ValueError('collection identity mismatch')
    by_path = {a.path: a for a in artifacts}
    if len(by_path) != len(artifacts):
        raise ValueError('duplicate source artifact references')
    frames = []
    for frame in collection.frames:
        requested = Path(frame.output_path)
        contained(layout, requested)  # Validate resolved containment without discarding the recorded path.
        relative = requested.relative_to(layout.root).as_posix() if requested.is_absolute() else requested.as_posix()
        artifact = by_path.get(relative)
        frames.append(CoverageFrame(data_time=frame.data_time, path=relative,
                      bytes=artifact.bytes if artifact else frame.bytes_written,
                      sha256=artifact.sha256 if artifact else None))
    return frames


def _entry(layout: DataLayout, *, event_id: str, data_id: str, start: str, end: str,
           cadence: int, units: str, crs: str, collection: ArtifactRecord | None,
           artifacts: list[ArtifactRecord], attempts: list[SourceAttempt]) -> tuple[CoverageEntry, str]:
    state = 'verified'
    try:
        frames = _frames(layout, collection, artifacts, event_id, data_id)
    except FAILURES:
        state, frames = 'invalid', []
    entry = CoverageEntry.model_validate({'event_id': event_id, 'data_id': data_id,
        'start_time': start, 'end_time': end, 'cadence_minutes': cadence, 'units': units,
        'crs': crs, 'frames': [f.model_dump() for f in frames],
        'attempts': [a.model_dump() for a in attempts]})
    return entry, state


def _attempts(candidate) -> list[SourceAttempt]:
    attempts = []
    for capture in candidate.evidence_captures:
        for source in (capture.qpe, capture.gauges, capture.warnings):
            if source.status != 'error':
                continue
            match = re.search(r'\bHTTP\s+(\d{3})\b', source.failure_reason or '', re.I)
            status = int(match.group(1)) if match else None
            kind = source.failure_kind or 'unknown'
            known = {'http', 'authentication', 'rate_limit', 'transport', 'timeout'}
            attempts.append(SourceAttempt(data_time=capture.target_data_time,
                attempted_at=capture.captured_at, data_id=source.dataset_id,
                http_status=status, failure_kind=kind if kind in known else 'unknown'))
    return attempts


def _discovery(layout: DataLayout, raw: bytes, limit: int):
    catalog = EventEvidenceCatalog.model_validate_json(raw)
    if Path(catalog.data_root).resolve() != layout.root:
        raise ValueError('data root differs')
    entries = []
    for c in catalog.candidates[:limit]:
        entries.append(_entry(layout, event_id=c.candidate_id, data_id=c.source_data_id,
            start=c.window_start_time, end=c.window_end_time, cadence=catalog.config.cadence_minutes,
            units='dBZ', crs='TWD67', collection=c.radar_collection.collection,
            artifacts=list(c.radar_collection.frames), attempts=_attempts(c)))
    return entries, max(0, len(catalog.candidates) - limit), 'event_evidence_catalog'


def _dataset(layout: DataLayout, raw: bytes, limit: int):
    catalog = DatasetCatalog.model_validate_json(raw)
    if Path(catalog.data_root).resolve() != layout.root:
        raise ValueError('data root differs')
    manifest = RadarDatasetManifest.model_validate_json(_metadata(layout, catalog.manifest))
    config = manifest.dataset
    entries = []
    for e in catalog.events[:limit]:
        collections = [a for a in e.artifacts if a.kind == 'event_collection']
        collection = collections[0] if len(collections) == 1 else None
        artifacts = [a for a in e.artifacts if a.kind == 'raw_radar_frame']
        entries.append(_entry(layout, event_id=e.event_id, data_id=e.source_data_id,
            start=e.start_time, end=e.end_time, cadence=config.cadence_minutes,
            units=config.units, crs=config.crs, collection=collection, artifacts=artifacts, attempts=[]))
    return entries, max(0, len(catalog.events) - limit), 'dataset_catalog'


def load_inventory(layout: DataLayout, path: Path, limit: int) -> LoadedInventory:
    try:
        raw = contained(layout, path).read_bytes()
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('inventory must be an object')
        if payload.get('kind') == 'archive_inventory':
            inventory = ArchiveInventory.model_validate_json(raw)
            entries = [(e, 'declared') for e in inventory.entries[:limit]]
            omitted, kind = max(0, len(inventory.entries) - limit), 'archive_inventory'
        elif 'candidates' in payload:
            entries, omitted, kind = _discovery(layout, raw, limit)
        else:
            entries, omitted, kind = _dataset(layout, raw, limit)
        if sum(len(entry.times()) for entry, _ in entries) > 100000:
            raise ValueError('excessive schedule')
        return LoadedInventory(entries, hashlib.sha256(raw).hexdigest(), omitted, kind)
    except FAILURES:
        raise ValueError(INVENTORY_ERROR) from None
