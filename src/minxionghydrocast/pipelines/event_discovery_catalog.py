"""Catalog, timestamp, and artifact-integrity helpers for event discovery."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from minxionghydrocast.ingestion.cwa_history import CwaHistoryFile, CwaHistoryIndex
from minxionghydrocast.io.research_store import ResearchLayout, sha256_file
from minxionghydrocast.models.dataset_schemas import ArtifactRecord
from minxionghydrocast.models.event_evidence_schemas import (
    DiscoveryConfig,
    DiscoveryCursor,
    EventEvidenceCatalog,
    aware_datetime,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def iso_seconds(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.isoformat(timespec="seconds")


def _unique_history_files(index: CwaHistoryIndex) -> tuple[CwaHistoryFile, ...]:
    by_time: dict[datetime, CwaHistoryFile] = {}
    for item in index.files:
        if not item.data_time:
            continue
        parsed = aware_datetime(item.data_time, field="history data_time")
        by_time.setdefault(parsed, item)
    return tuple(by_time[key] for key in sorted(by_time))


def _history_with_files(
    index: CwaHistoryIndex,
    files: tuple[CwaHistoryFile, ...],
) -> CwaHistoryIndex:
    return index.model_copy(update={"files": files, "file_count": len(files)})


def _normalized_history_index(index: CwaHistoryIndex) -> CwaHistoryIndex:
    files = tuple(item.model_copy(update={"raw": {}}) for item in _unique_history_files(index))
    return CwaHistoryIndex.model_validate(
        index.model_dump(mode="python")
        | {
            "files": files,
            "file_count": len(files),
            "raw": {},
        }
    )


def _history_artifact_path(layout: ResearchLayout, index: CwaHistoryIndex) -> Path:
    files = _unique_history_files(index)
    latest = (
        aware_datetime(files[-1].data_time, field="history data_time").strftime(
            "%Y%m%dT%H%M%S%z"
        )
        if files
        else "empty"
    )
    content_hash = index.model_dump_json().encode("utf-8")
    suffix = hashlib.sha256(content_hash).hexdigest()[:12]
    return layout.discovery_history / f"{index.data_id}_{latest}_{suffix}.json"


def load_event_evidence_catalog(path: Path) -> EventEvidenceCatalog:
    return EventEvidenceCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def event_catalog_artifacts(catalog: EventEvidenceCatalog) -> tuple[ArtifactRecord, ...]:
    artifacts = list(catalog.history_indexes)
    for candidate in catalog.candidates:
        collection = candidate.radar_collection
        if collection.plan is not None:
            artifacts.append(collection.plan)
        if collection.collection is not None:
            artifacts.append(collection.collection)
        artifacts.extend(collection.frames)
        for capture in candidate.evidence_captures:
            for source in (capture.qpe, capture.gauges, capture.warnings):
                if source.artifact is not None:
                    artifacts.append(source.artifact)
        if candidate.review is not None:
            artifacts.extend(
                context.artifact for context in candidate.review.official_context_artifacts
            )
    return tuple(artifacts)


def artifact_matches(layout: ResearchLayout, artifact: ArtifactRecord) -> bool:
    try:
        path = layout.resolve_relative(artifact.path)
    except ValueError:
        return False
    return (
        path.is_file()
        and path.stat().st_size == artifact.bytes
        and sha256_file(path) == artifact.sha256
    )


def verify_event_evidence_catalog(
    catalog: EventEvidenceCatalog,
    *,
    layout: ResearchLayout,
) -> tuple[str, ...]:
    errors = []
    seen: set[str] = set()
    for artifact in event_catalog_artifacts(catalog):
        if artifact.path in seen:
            errors.append(f"duplicate artifact path: {artifact.path}")
            continue
        seen.add(artifact.path)
        try:
            path = layout.resolve_relative(artifact.path)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing artifact: {artifact.path}")
            continue
        if path.stat().st_size != artifact.bytes:
            errors.append(f"size mismatch: {artifact.path}")
            continue
        if sha256_file(path) != artifact.sha256:
            errors.append(f"sha256 mismatch: {artifact.path}")
    return tuple(errors)


def _new_catalog(
    *,
    layout: ResearchLayout,
    config: DiscoveryConfig,
    now: datetime,
) -> EventEvidenceCatalog:
    return EventEvidenceCatalog(
        updated_at=iso_seconds(now),
        data_root=str(layout.root),
        config=config,
        cursor=DiscoveryCursor(),
    )


def _load_or_create_catalog(
    *,
    path: Path,
    layout: ResearchLayout,
    config: DiscoveryConfig,
    now: datetime,
) -> tuple[EventEvidenceCatalog, bool]:
    if not path.is_file():
        return _new_catalog(layout=layout, config=config, now=now), True
    catalog = load_event_evidence_catalog(path)
    if Path(catalog.data_root).resolve() != layout.root:
        raise ValueError("event evidence catalog data_root does not match configuration")
    if catalog.config != config:
        raise ValueError(
            "event discovery configuration changed; migrate the catalog explicitly before rerunning"
        )
    return catalog, False


def _catalog_content(catalog: EventEvidenceCatalog) -> dict[str, object]:
    return catalog.model_dump(mode="json", exclude={"updated_at"})
