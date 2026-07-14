"""Continuously discover radar events and preserve synchronized evidence."""

from __future__ import annotations

import argparse
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion.cwa_event_collector import (
    CwaCollectedFrame,
    CwaEventCollection,
    CwaEventFrame,
    CwaEventPlan,
    build_event_plan,
    download_event_frames,
    load_event_collection,
)
from minxionghydrocast.ingestion.cwa_file_api import (
    CwaDownloadRequest,
    download_cwa_file,
)
from minxionghydrocast.ingestion.cwa_grid import inspect_cwa_grid_file
from minxionghydrocast.ingestion.cwa_history import (
    CwaHistoryFile,
    CwaHistoryIndex,
    CwaHistoryRequest,
    fetch_history_index,
)
from minxionghydrocast.ingestion.cwa_rainfall_api import CwaRainGaugeAdapter
from minxionghydrocast.ingestion.http_client import verified_get
from minxionghydrocast.ingestion.source_adapter import SourceAdapterError, SourceResult
from minxionghydrocast.ingestion.wra_rainfall_alert_api import WraRainfallAlertAdapter
from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    prune_cache,
    require_external_research_root,
    sha256_file,
    write_schema_if_changed,
)
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.event_evidence_schemas import (
    CandidateRadarCollection,
    CoverageMetric,
    DiscoveryConfig,
    DiscoveryCursor,
    EventCandidate,
    EventEvidenceCatalog,
    EvidenceSourceRecord,
    NormalizedSourceSnapshot,
    RadarFrameMetric,
    SynchronizedEvidenceCapture,
    aware_datetime,
)
from minxionghydrocast.models.dataset_schemas import ArtifactRecord
from minxionghydrocast.pipelines.radar_event_summary import EventFramePath, summarize_frame

PIPELINE_NAME = "event_discover"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
CATALOG_NAME = "event_evidence_catalog.json"
DEFAULT_CACHE_RETENTION_HOURS = 48.0
DEFAULT_CACHE_MAX_BYTES = 10 * 1024 * 1024 * 1024
LOGGER = logging.getLogger(__name__)


class HistoryHttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> object: ...


class FrameHttpGet(Protocol):
    def __call__(self, url: str, *, timeout: int, verify: bool) -> object: ...


class FileHttpGet(Protocol):
    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        timeout: int,
        verify: bool,
    ) -> object: ...


@dataclass(frozen=True)
class EventDiscoveryResult:
    catalog_path: Path
    catalog_changed: bool
    scanned_frame_count: int
    trigger_frame_count: int
    candidate_count: int
    complete_candidate_count: int
    evidence_error_count: int
    cache_files_removed: int
    cache_bytes_removed: int


def _verified_history_get(
    url: str,
    *,
    params: dict[str, str],
    timeout: int,
    verify: bool,
) -> object:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return verified_get(url, params=params, headers=None, timeout=float(timeout))


def _verified_frame_get(url: str, *, timeout: int, verify: bool) -> object:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return verified_get(url, params={}, headers=None, timeout=float(timeout))


def _verified_file_get(
    url: str,
    *,
    params: dict[str, str],
    timeout: int,
    verify: bool,
) -> object:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return verified_get(url, params=params, headers=None, timeout=float(timeout))


def _fetch_history_with_retry(
    *,
    config: DiscoveryConfig,
    authorization: str,
    timeout: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    history_http_get: HistoryHttpGet,
) -> CwaHistoryIndex:
    for attempt in range(1, retry_attempts + 1):
        try:
            return fetch_history_index(
                CwaHistoryRequest(data_id=config.radar_data_id),
                authorization=authorization,
                timeout=timeout,
                http_get=history_http_get,
                verify_tls=True,
            )
        except Exception as exc:
            if attempt == retry_attempts:
                raise RuntimeError(
                    f"CWA history request failed after {attempt} attempts: {type(exc).__name__}"
                ) from exc
            time.sleep(retry_backoff_seconds * (2 ** (attempt - 1)))
    raise AssertionError("CWA history retry loop terminated unexpectedly")


def now_taipei() -> datetime:
    return datetime.now(TAIPEI_TZ)


def iso_seconds(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return value.isoformat(timespec="seconds")


def expected_data_times(
    start_time: str,
    end_time: str,
    *,
    cadence_minutes: int,
) -> tuple[str, ...]:
    start = aware_datetime(start_time, field="window_start_time")
    end = aware_datetime(end_time, field="window_end_time")
    if end <= start:
        raise ValueError("event window end must be after start")
    step = timedelta(minutes=cadence_minutes)
    values = []
    current = start
    while current <= end:
        values.append(iso_seconds(current))
        current += step
    if current - step != end:
        raise ValueError("event window is not cadence aligned")
    return tuple(values)


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
    files = tuple(
        item.model_copy(update={"raw": {}})
        for item in _unique_history_files(index)
    )
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
        aware_datetime(files[-1].data_time, field="history data_time").strftime("%Y%m%dT%H%M%S%z")
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
                context.artifact
                for context in candidate.review.official_context_artifacts
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
        research_root=str(layout.root),
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
    if Path(catalog.research_root).resolve() != layout.root:
        raise ValueError("event evidence catalog research_root does not match configuration")
    if catalog.config != config:
        raise ValueError(
            "event discovery configuration changed; migrate the catalog explicitly before rerunning"
        )
    return catalog, False


def _scan_files(
    *,
    index: CwaHistoryIndex,
    cursor: DiscoveryCursor,
    config: DiscoveryConfig,
) -> tuple[CwaHistoryFile, ...]:
    files = _unique_history_files(index)
    if not files:
        return ()
    if cursor.last_scanned_data_time is not None:
        last_scanned = aware_datetime(
            cursor.last_scanned_data_time,
            field="last_scanned_data_time",
        )
        return tuple(
            item
            for item in files
            if aware_datetime(item.data_time, field="history data_time") > last_scanned
        )
    latest = aware_datetime(files[-1].data_time, field="history data_time")
    earliest = latest - timedelta(minutes=config.initial_lookback_minutes)
    return tuple(
        item
        for item in files
        if aware_datetime(item.data_time, field="history data_time") >= earliest
    )


def _coverage_metric(
    payload: object,
    *,
    valid_pixel_count: int | None = None,
) -> CoverageMetric:
    if not isinstance(payload, dict):
        raise ValueError("radar coverage summary section must be an object")
    return CoverageMetric(
        valid_pixel_count=(
            int(payload["valid_pixel_count"])
            if valid_pixel_count is None
            else valid_pixel_count
        ),
        pixels_ge_threshold=int(payload["pixels_ge_threshold"]),
        fraction_ge_threshold=float(payload["fraction_ge_threshold"]),
        max_value=float(payload["max_value"]) if payload.get("max_value") is not None else None,
    )


def _metric_from_frame(
    *,
    path: Path,
    data_time: str,
    config: DiscoveryConfig,
) -> RadarFrameMetric:
    payload, inspection = summarize_frame(
        EventFramePath(data_time=data_time, path=path),
        local_longitude=config.local_longitude,
        local_latitude=config.local_latitude,
        local_radius_pixels=config.local_radius_pixels,
        event_threshold=config.event_threshold_dbz,
    )
    if inspection.data_id != config.radar_data_id or inspection.units != "dBZ":
        raise ValueError(
            f"unexpected radar grid contract: data_id={inspection.data_id} units={inspection.units}"
        )
    if aware_datetime(inspection.data_time, field="radar data_time") != aware_datetime(
        data_time,
        field="history data_time",
    ):
        raise ValueError("downloaded radar grid data_time does not match history metadata")
    local = _coverage_metric(payload["local_focus"])
    grid = payload["grid"]
    if not isinstance(grid, dict):
        raise ValueError("radar grid summary must be an object")
    taiwan = _coverage_metric(
        payload["taiwan_wide"],
        valid_pixel_count=int(grid["valid_pixel_count"]),
    )
    labels = []
    if local.pixels_ge_threshold >= config.local_min_pixels:
        labels.append("minxiong_35dbz")
    if taiwan.pixels_ge_threshold >= config.taiwan_min_pixels:
        labels.append("taiwan_wide_35dbz")
    return RadarFrameMetric(
        data_time=iso_seconds(aware_datetime(inspection.data_time, field="radar data_time")),
        source_sha256=sha256_file(path),
        source_bytes=path.stat().st_size,
        threshold_dbz=config.event_threshold_dbz,
        local=local,
        taiwan=taiwan,
        candidate_labels=tuple(labels),
    )


def _empty_collection(
    *,
    start_time: str,
    end_time: str,
    config: DiscoveryConfig,
) -> CandidateRadarCollection:
    missing = expected_data_times(
        start_time,
        end_time,
        cadence_minutes=config.cadence_minutes,
    )
    return CandidateRadarCollection(
        expected_frame_count=len(missing),
        captured_frame_count=0,
        missing_data_times=missing,
    )


def _extended_collection(
    candidate: EventCandidate,
    *,
    end_time: str,
    config: DiscoveryConfig,
) -> CandidateRadarCollection:
    previous_expected = expected_data_times(
        candidate.window_start_time,
        candidate.window_end_time,
        cadence_minutes=config.cadence_minutes,
    )
    extended_expected = expected_data_times(
        candidate.window_start_time,
        end_time,
        cadence_minutes=config.cadence_minutes,
    )
    previous_missing = set(candidate.radar_collection.missing_data_times)
    added = set(extended_expected) - set(previous_expected)
    missing = tuple(value for value in extended_expected if value in previous_missing | added)
    return CandidateRadarCollection(
        expected_frame_count=len(extended_expected),
        captured_frame_count=candidate.radar_collection.captured_frame_count,
        missing_data_times=missing,
        plan=candidate.radar_collection.plan,
        collection=candidate.radar_collection.collection,
        frames=candidate.radar_collection.frames,
        complete=False,
    )


def _candidate_id(data_time: str) -> str:
    parsed = aware_datetime(data_time, field="candidate data_time")
    return f"cwa_o_a0059_candidate_{parsed:%Y%m%dt%H%M}"


def apply_trigger_metrics(
    candidates: tuple[EventCandidate, ...],
    *,
    metrics: tuple[RadarFrameMetric, ...],
    config: DiscoveryConfig,
) -> tuple[EventCandidate, ...]:
    updated = list(candidates)
    known_times = {trigger.data_time for candidate in updated for trigger in candidate.triggers}
    for metric in sorted(metrics, key=lambda item: aware_datetime(item.data_time, field="metric")):
        if not metric.candidate_labels or metric.data_time in known_times:
            continue
        metric_time = aware_datetime(metric.data_time, field="metric data_time")
        target_index = None
        for index in range(len(updated) - 1, -1, -1):
            candidate = updated[index]
            if candidate.review_status != "pending":
                continue
            gap = metric_time - aware_datetime(
                candidate.last_trigger_time,
                field="last_trigger_time",
            )
            proposed_end = metric_time + timedelta(minutes=config.after_minutes)
            proposed_window = proposed_end - aware_datetime(
                candidate.window_start_time,
                field="window_start_time",
            )
            if (
                timedelta(0) < gap <= timedelta(minutes=config.merge_gap_minutes)
                and proposed_window
                <= timedelta(minutes=config.max_candidate_window_minutes)
            ):
                target_index = index
                break
        if target_index is None:
            start = metric_time - timedelta(minutes=config.before_minutes)
            end = metric_time + timedelta(minutes=config.after_minutes)
            updated.append(
                EventCandidate(
                    candidate_id=_candidate_id(metric.data_time),
                    operational_status="collecting",
                    first_trigger_time=metric.data_time,
                    last_trigger_time=metric.data_time,
                    window_start_time=iso_seconds(start),
                    window_end_time=iso_seconds(end),
                    candidate_labels=metric.candidate_labels,
                    triggers=(metric,),
                    radar_collection=_empty_collection(
                        start_time=iso_seconds(start),
                        end_time=iso_seconds(end),
                        config=config,
                    ),
                )
            )
        else:
            candidate = updated[target_index]
            end = metric_time + timedelta(minutes=config.after_minutes)
            triggers = (*candidate.triggers, metric)
            labels = tuple(sorted({label for trigger in triggers for label in trigger.candidate_labels}))
            updated[target_index] = candidate.model_copy(
                update={
                    "operational_status": "collecting",
                    "last_trigger_time": metric.data_time,
                    "window_end_time": iso_seconds(end),
                    "candidate_labels": labels,
                    "triggers": triggers,
                    "radar_collection": _extended_collection(
                        candidate,
                        end_time=iso_seconds(end),
                        config=config,
                    ),
                }
            )
        known_times.add(metric.data_time)
    return tuple(updated)


def _merged_plan(path: Path, current: CwaEventPlan) -> CwaEventPlan:
    frames: dict[datetime, CwaEventFrame] = {}
    if path.is_file():
        previous = CwaEventPlan.model_validate_json(path.read_text(encoding="utf-8"))
        for frame in previous.frames:
            frames[aware_datetime(frame.data_time, field="event frame")] = frame
    for frame in current.frames:
        frames[aware_datetime(frame.data_time, field="event frame")] = frame
    ordered = tuple(frames[key] for key in sorted(frames))
    return current.model_copy(update={"frames": ordered, "frame_count": len(ordered)})


def _valid_previous_frames(
    candidate: EventCandidate,
    *,
    layout: ResearchLayout,
) -> dict[str, CwaCollectedFrame]:
    expected_artifacts = {artifact.path: artifact for artifact in candidate.radar_collection.frames}
    for relative, artifact in expected_artifacts.items():
        if artifact_matches(layout, artifact):
            continue
        try:
            layout.resolve_relative(relative).unlink(missing_ok=True)
        except ValueError:
            pass
    valid: dict[str, CwaCollectedFrame] = {}
    collection_artifact = candidate.radar_collection.collection
    if collection_artifact is None:
        return valid
    collection_path = layout.resolve_relative(collection_artifact.path)
    if not artifact_matches(layout, collection_artifact):
        collection_path.unlink(missing_ok=True)
        return valid
    try:
        collection = load_event_collection(collection_path)
    except Exception:
        collection_path.unlink(missing_ok=True)
        return valid
    for frame in collection.frames:
        path = Path(frame.output_path).resolve()
        try:
            relative = layout.relative(path)
        except ValueError:
            continue
        artifact = expected_artifacts.get(relative)
        if artifact is None or not path.is_file():
            continue
        if path.stat().st_size != artifact.bytes or sha256_file(path) != artifact.sha256:
            path.unlink(missing_ok=True)
            continue
        valid[frame.data_time] = frame
    return valid


def _refresh_candidate_collection(
    candidate: EventCandidate,
    *,
    history_index: CwaHistoryIndex,
    history_latest: datetime | None,
    layout: ResearchLayout,
    authorization: str,
    config: DiscoveryConfig,
    timeout: int,
    max_workers: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    frame_http_get: FrameHttpGet,
) -> EventCandidate:
    plan_path = layout.events / f"{candidate.candidate_id}_plan.json"
    collection_path = layout.events / f"{candidate.candidate_id}_collection.json"
    if (
        candidate.radar_collection.plan is not None
        and not artifact_matches(layout, candidate.radar_collection.plan)
    ):
        plan_path.unlink(missing_ok=True)
    current_plan = build_event_plan(
        history_index.model_dump(mode="json"),
        event_id=candidate.candidate_id,
        start_time=candidate.window_start_time,
        end_time=candidate.window_end_time,
    )
    plan = _merged_plan(plan_path, current_plan)
    write_schema_if_changed(plan_path, plan)

    collected = _valid_previous_frames(candidate, layout=layout)
    if current_plan.frames:
        current_collection = download_event_frames(
            current_plan,
            output_dir=layout.raw / "event_evidence",
            authorization=authorization,
            timeout=timeout,
            http_get=frame_http_get,
            skip_existing=True,
            max_workers=max_workers,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        for frame in current_collection.frames:
            collected[iso_seconds(aware_datetime(frame.data_time, field="collected frame"))] = (
                frame.model_copy(
                    update={
                        "data_time": iso_seconds(
                            aware_datetime(frame.data_time, field="collected frame")
                        )
                    }
                )
            )

    ordered_frames = tuple(
        collected[key]
        for key in sorted(collected, key=lambda value: aware_datetime(value, field="collection"))
        if Path(collected[key].output_path).is_file()
    )
    collection = None
    collection_artifact = None
    if ordered_frames:
        collection = CwaEventCollection(
            event_id=candidate.candidate_id,
            data_id=config.radar_data_id,
            frame_count=len(ordered_frames),
            bytes_written=sum(frame.bytes_written for frame in ordered_frames),
            frames=ordered_frames,
        )
        write_schema_if_changed(collection_path, collection)
        collection_artifact = artifact_record(
            layout,
            collection_path,
            kind="candidate_radar_collection",
        )

    expected = expected_data_times(
        candidate.window_start_time,
        candidate.window_end_time,
        cadence_minutes=config.cadence_minutes,
    )
    captured_by_time = {
        iso_seconds(aware_datetime(frame.data_time, field="collected frame")): frame
        for frame in ordered_frames
    }
    missing = tuple(value for value in expected if value not in captured_by_time)
    frame_artifacts = tuple(
        artifact_record(
            layout,
            Path(captured_by_time[value].output_path),
            kind="candidate_radar_frame",
        )
        for value in expected
        if value in captured_by_time
    )
    complete = not missing
    if complete:
        operational_status = "awaiting_review"
    elif history_latest is not None and history_latest >= aware_datetime(
        candidate.window_end_time,
        field="window_end_time",
    ):
        operational_status = "incomplete"
    else:
        operational_status = "collecting"
    radar_collection = CandidateRadarCollection(
        expected_frame_count=len(expected),
        captured_frame_count=len(frame_artifacts),
        missing_data_times=missing,
        plan=artifact_record(layout, plan_path, kind="candidate_radar_plan"),
        collection=collection_artifact,
        frames=frame_artifacts,
        complete=complete,
    )
    return candidate.model_copy(
        update={
            "operational_status": operational_status,
            "radar_collection": radar_collection,
        }
    )


def _observed_at(records: list[dict[str, str]]) -> str | None:
    timestamps = []
    for record in records:
        value = record.get("水情時間ISO") or record.get("資料產出時間ISO")
        if value:
            timestamps.append(aware_datetime(value, field="evidence observed time"))
    return iso_seconds(max(timestamps)) if timestamps else None


def _alignment_delta(target_data_time: str, observed_at: str | None) -> float | None:
    if observed_at is None:
        return None
    target = aware_datetime(target_data_time, field="target_data_time")
    observed = aware_datetime(observed_at, field="observed_at")
    return round(abs((observed - target).total_seconds()) / 60, 3)


def _source_record_from_snapshot(
    snapshot: NormalizedSourceSnapshot,
    *,
    artifact: ArtifactRecord,
    max_alignment_minutes: int,
) -> EvidenceSourceRecord:
    observed = _observed_at(snapshot.records)
    alignment_delta = _alignment_delta(snapshot.target_data_time, observed)
    status = snapshot.provenance.outcome
    if (
        status == "ok"
        and alignment_delta is not None
        and alignment_delta > max_alignment_minutes
    ):
        status = "stale"
    return EvidenceSourceRecord(
        dataset_id=snapshot.provenance.dataset_id,
        status=status,
        observed_at=observed,
        alignment_delta_minutes=alignment_delta,
        artifact=artifact,
        provenance=snapshot.provenance,
    )


def _capture_normalized_source(
    *,
    candidate_id: str,
    target_data_time: str,
    output_path: Path,
    artifact_kind: str,
    expected_data_id: str,
    collector: Callable[[], SourceResult],
    layout: ResearchLayout,
    max_alignment_minutes: int,
) -> EvidenceSourceRecord:
    if output_path.is_file():
        try:
            snapshot = NormalizedSourceSnapshot.model_validate_json(
                output_path.read_text(encoding="utf-8")
            )
        except Exception:
            output_path.unlink(missing_ok=True)
            raise
    else:
        result = collector()
        if result.provenance.dataset_id != expected_data_id:
            raise ValueError(
                f"unexpected evidence dataset {result.provenance.dataset_id}; expected {expected_data_id}"
            )
        snapshot = NormalizedSourceSnapshot(
            candidate_id=candidate_id,
            target_data_time=target_data_time,
            dataset=result.dataset,
            records=result.records,
            provenance=result.provenance,
        )
        write_schema_if_changed(output_path, snapshot)
    return _source_record_from_snapshot(
        snapshot,
        artifact=artifact_record(layout, output_path, kind=artifact_kind),
        max_alignment_minutes=max_alignment_minutes,
    )


def _capture_qpe(
    *,
    target_data_time: str,
    output_path: Path,
    authorization: str,
    layout: ResearchLayout,
    timeout: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    qpe_http_get: FileHttpGet,
    max_alignment_minutes: int,
) -> EvidenceSourceRecord:
    if not output_path.is_file():
        download_cwa_file(
            CwaDownloadRequest(data_id="O-B0045-001", file_format="JSON"),
            authorization=authorization,
            output_path=output_path,
            timeout=timeout,
            http_get=qpe_http_get,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    try:
        inspection = inspect_cwa_grid_file(output_path)
    except Exception:
        output_path.unlink(missing_ok=True)
        raise
    if inspection.data_id != "O-B0045-001" or not inspection.valid:
        output_path.unlink(missing_ok=True)
        raise ValueError("O-B0045-001 QPE grid failed its structural contract")
    observed = iso_seconds(aware_datetime(inspection.data_time, field="QPE data_time"))
    alignment_delta = _alignment_delta(target_data_time, observed)
    return EvidenceSourceRecord(
        dataset_id="O-B0045-001",
        status=(
            "stale"
            if alignment_delta is not None and alignment_delta > max_alignment_minutes
            else "ok"
        ),
        observed_at=observed,
        alignment_delta_minutes=alignment_delta,
        artifact=artifact_record(layout, output_path, kind="qpe_grid_evidence"),
    )


def _safe_failure_reason(exc: Exception, *, secrets: tuple[str, ...]) -> str:
    reason = f"{type(exc).__name__}: {exc}"
    for secret in secrets:
        if secret:
            reason = reason.replace(secret, "REDACTED")
    return reason[:500]


def _error_record(
    dataset_id: str,
    exc: Exception,
    *,
    secrets: tuple[str, ...],
) -> EvidenceSourceRecord:
    kind = exc.kind if isinstance(exc, SourceAdapterError) else type(exc).__name__
    return EvidenceSourceRecord(
        dataset_id=dataset_id,
        status="error",
        failure_kind=str(kind),
        failure_reason=_safe_failure_reason(exc, secrets=secrets),
    )


def _mark_corrupt_evidence(
    candidate: EventCandidate,
    *,
    layout: ResearchLayout,
) -> EventCandidate:
    captures = []
    changed = False
    for capture in candidate.evidence_captures:
        sources = {}
        for name, source in (
            ("qpe", capture.qpe),
            ("gauges", capture.gauges),
            ("warnings", capture.warnings),
        ):
            if source.artifact is None or artifact_matches(layout, source.artifact):
                sources[name] = source
                continue
            try:
                layout.resolve_relative(source.artifact.path).unlink(missing_ok=True)
            except ValueError:
                pass
            sources[name] = EvidenceSourceRecord(
                dataset_id=source.dataset_id,
                status="error",
                failure_kind="checksum_mismatch",
                failure_reason="cataloged evidence artifact failed SHA-256 verification",
            )
            changed = True
        captures.append(
            SynchronizedEvidenceCapture.model_validate(
                capture.model_dump(mode="python") | sources
            )
        )
    if not changed:
        return candidate
    # A reviewed candidate may be temporarily invalid while its corrupt evidence is retried.
    return candidate.model_copy(update={"evidence_captures": tuple(captures)})


def _capture_evidence(
    candidate: EventCandidate,
    *,
    target_data_time: str,
    layout: ResearchLayout,
    now: datetime,
    cwa_api_key: str,
    wra_api_key: str,
    county_code: str,
    county_name: str,
    timeout: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    qpe_http_get: FileHttpGet,
    gauge_collector: Callable[[], SourceResult],
    warning_collector: Callable[[], SourceResult],
    max_alignment_minutes: int,
) -> EventCandidate:
    target = target_data_time
    capture_id = f"{candidate.candidate_id}_{aware_datetime(target, field='target'):%Y%m%dt%H%M}"
    captures = list(candidate.evidence_captures)
    existing_index = next(
        (index for index, capture in enumerate(captures) if capture.capture_id == capture_id),
        None,
    )
    if existing_index is not None:
        existing = captures[existing_index]
        if all(
            source.status != "error"
            for source in (existing.qpe, existing.gauges, existing.warnings)
        ):
            return candidate
    else:
        existing = None

    capture_dir = layout.evidence / candidate.candidate_id / capture_id
    secrets = (cwa_api_key, wra_api_key)

    if existing is not None and existing.qpe.status != "error":
        qpe = existing.qpe
    else:
        try:
            qpe = _capture_qpe(
                target_data_time=target,
                output_path=capture_dir / "O-B0045-001.json",
                authorization=cwa_api_key,
                layout=layout,
                timeout=timeout,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                qpe_http_get=qpe_http_get,
                max_alignment_minutes=max_alignment_minutes,
            )
        except Exception as exc:
            qpe = _error_record("O-B0045-001", exc, secrets=secrets)

    if existing is not None and existing.gauges.status != "error":
        gauges = existing.gauges
    else:
        try:
            gauges = _capture_normalized_source(
                candidate_id=candidate.candidate_id,
                target_data_time=target,
                output_path=capture_dir / "O-A0002-001.json",
                artifact_kind="rain_gauge_evidence",
                expected_data_id="O-A0002-001",
                collector=gauge_collector,
                layout=layout,
                max_alignment_minutes=max_alignment_minutes,
            )
        except Exception as exc:
            gauges = _error_record("O-A0002-001", exc, secrets=secrets)

    if existing is not None and existing.warnings.status != "error":
        warnings = existing.warnings
    else:
        try:
            warnings = _capture_normalized_source(
                candidate_id=candidate.candidate_id,
                target_data_time=target,
                output_path=capture_dir / "WRA-Rainfall-Warning.json",
                artifact_kind="rainfall_warning_evidence",
                expected_data_id="WRA-Rainfall-Warning-v2",
                collector=warning_collector,
                layout=layout,
                max_alignment_minutes=max_alignment_minutes,
            )
        except Exception as exc:
            warnings = _error_record("WRA-Rainfall-Warning-v2", exc, secrets=secrets)

    capture = SynchronizedEvidenceCapture(
        capture_id=capture_id,
        target_data_time=target,
        captured_at=iso_seconds(now),
        qpe=qpe,
        gauges=gauges,
        warnings=warnings,
    )
    if existing_index is None:
        captures.append(capture)
    else:
        captures[existing_index] = capture
    return candidate.model_copy(update={"evidence_captures": tuple(captures)})


def _catalog_content(catalog: EventEvidenceCatalog) -> dict[str, object]:
    return catalog.model_dump(mode="json", exclude={"updated_at"})


def run_event_discovery(
    *,
    repository_root: Path,
    research_root: Path,
    cwa_api_key: str,
    wra_api_key: str,
    config: DiscoveryConfig,
    county_code: str = "10010",
    county_name: str = "嘉義縣",
    timeout: int = 60,
    max_workers: int = 2,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 1.0,
    cache_retention_hours: float = DEFAULT_CACHE_RETENTION_HOURS,
    cache_max_bytes: int = DEFAULT_CACHE_MAX_BYTES,
    now: datetime | None = None,
    history_index: CwaHistoryIndex | None = None,
    history_http_get: HistoryHttpGet = _verified_history_get,
    frame_http_get: FrameHttpGet = _verified_frame_get,
    qpe_http_get: FileHttpGet = _verified_file_get,
    gauge_collector: Callable[[], SourceResult] | None = None,
    warning_collector: Callable[[], SourceResult] | None = None,
) -> EventDiscoveryResult:
    if not cwa_api_key:
        raise ValueError("missing CWA_API_KEY")
    if not wra_api_key:
        raise ValueError("missing WRA_API_KEY")
    if timeout <= 0 or max_workers < 1 or retry_attempts < 1:
        raise ValueError("timeout, max_workers, and retry_attempts must be positive")
    current_time = (now or now_taipei()).astimezone(TAIPEI_TZ)
    layout = ResearchLayout(research_root)
    require_external_research_root(layout, repository_root=repository_root)
    layout.ensure()
    catalog_path = layout.discovery / CATALOG_NAME

    with layout.event_discovery_lock():
        catalog, catalog_is_new = _load_or_create_catalog(
            path=catalog_path,
            layout=layout,
            config=config,
            now=current_time,
        )
        original_content = _catalog_content(catalog)
        if history_index is None:
            history_index = _fetch_history_with_retry(
                config=config,
                authorization=cwa_api_key,
                timeout=timeout,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                history_http_get=history_http_get,
            )
        history_index = _normalized_history_index(history_index)
        history_artifacts = {artifact.path: artifact for artifact in catalog.history_indexes}
        scan_files = _scan_files(index=history_index, cursor=catalog.cursor, config=config)
        metrics: list[RadarFrameMetric] = []
        if scan_files:
            scan_index = _history_with_files(history_index, scan_files)
            history_path = _history_artifact_path(layout, scan_index)
            write_schema_if_changed(history_path, scan_index)
            history_artifact = artifact_record(
                layout,
                history_path,
                kind="cwa_incremental_history_index",
            )
            history_artifacts[history_artifact.path] = history_artifact
            first_time = aware_datetime(scan_files[0].data_time, field="scan frame")
            last_time = aware_datetime(scan_files[-1].data_time, field="scan frame")
            scan_id = f"scan_{first_time:%Y%m%dt%H%M}_{last_time:%Y%m%dt%H%M}"
            scan_plan = build_event_plan(
                scan_index.model_dump(mode="json"),
                event_id=scan_id,
                start_time=iso_seconds(first_time),
                end_time=iso_seconds(last_time),
            )
            scan_collection = download_event_frames(
                scan_plan,
                output_dir=layout.discovery_cache,
                authorization=cwa_api_key,
                timeout=timeout,
                http_get=frame_http_get,
                overwrite=True,
                max_workers=max_workers,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            for frame in scan_collection.frames:
                metric = _metric_from_frame(
                    path=Path(frame.output_path),
                    data_time=frame.data_time,
                    config=config,
                )
                metric_path = layout.discovery_metrics / (
                    f"{aware_datetime(metric.data_time, field='metric'):%Y%m%dT%H%M%S%z}.json"
                )
                write_schema_if_changed(metric_path, metric)
                metrics.append(metric)

        candidates = apply_trigger_metrics(
            catalog.candidates,
            metrics=tuple(metrics),
            config=config,
        )
        latest_history_time = (
            aware_datetime(history_index.files[-1].data_time, field="history latest")
            if history_index.files
            else None
        )
        refreshed = []
        for candidate in candidates:
            candidate = _mark_corrupt_evidence(candidate, layout=layout)
            updated = _refresh_candidate_collection(
                candidate,
                history_index=history_index,
                history_latest=latest_history_time,
                layout=layout,
                authorization=cwa_api_key,
                config=config,
                timeout=timeout,
                max_workers=max_workers,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                frame_http_get=frame_http_get,
            )
            retry_targets = [
                capture.target_data_time
                for capture in updated.evidence_captures
                if any(
                    source.status == "error"
                    for source in (capture.qpe, capture.gauges, capture.warnings)
                )
            ]
            if not any(
                capture.target_data_time == updated.last_trigger_time
                for capture in updated.evidence_captures
            ):
                retry_targets.append(updated.last_trigger_time)
            for target_data_time in dict.fromkeys(retry_targets):
                gauge_collect = gauge_collector or (
                    lambda: CwaRainGaugeAdapter(
                        authorization=cwa_api_key,
                        county_code=county_code,
                        county_name=county_name,
                        timeout_seconds=float(timeout),
                    ).collect()
                )
                warning_collect = warning_collector or (
                    lambda: WraRainfallAlertAdapter(
                        api_key=wra_api_key,
                        county_code=county_code,
                        timeout_seconds=float(timeout),
                    ).collect()
                )
                updated = _capture_evidence(
                    updated,
                    target_data_time=target_data_time,
                    layout=layout,
                    now=current_time,
                    cwa_api_key=cwa_api_key,
                    wra_api_key=wra_api_key,
                    county_code=county_code,
                    county_name=county_name,
                    timeout=timeout,
                    retry_attempts=retry_attempts,
                    retry_backoff_seconds=retry_backoff_seconds,
                    qpe_http_get=qpe_http_get,
                    gauge_collector=gauge_collect,
                    warning_collector=warning_collect,
                    max_alignment_minutes=config.evidence_max_alignment_minutes,
                )
            refreshed.append(updated)

        cursor = catalog.cursor
        if metrics:
            cursor = DiscoveryCursor(
                last_scanned_data_time=max(
                    (metric.data_time for metric in metrics),
                    key=lambda value: aware_datetime(value, field="metric"),
                ),
                last_successful_scan_at=iso_seconds(current_time),
            )
        candidate_catalog = EventEvidenceCatalog.model_validate(
            catalog.model_dump(mode="python")
            | {
                "cursor": cursor,
                "history_indexes": tuple(
                    history_artifacts[path] for path in sorted(history_artifacts)
                ),
                "candidates": tuple(refreshed),
            }
        )
        changed = catalog_is_new or _catalog_content(candidate_catalog) != original_content
        verification_errors = verify_event_evidence_catalog(
            candidate_catalog,
            layout=layout,
        )
        if verification_errors:
            raise RuntimeError(
                "event evidence catalog verification failed: " + "; ".join(verification_errors)
            )
        if changed:
            candidate_catalog = EventEvidenceCatalog.model_validate(
                candidate_catalog.model_dump(mode="python")
                | {"updated_at": iso_seconds(current_time)}
            )
            write_schema_if_changed(catalog_path, candidate_catalog)

        removed_files, removed_bytes = prune_cache(
            layout.discovery_cache,
            max_age_seconds=cache_retention_hours * 3600,
            max_bytes=cache_max_bytes,
            now_timestamp=current_time.timestamp(),
        )
        evidence_errors = sum(
            source.status == "error"
            for candidate in candidate_catalog.candidates
            for capture in candidate.evidence_captures
            for source in (capture.qpe, capture.gauges, capture.warnings)
        )
        return EventDiscoveryResult(
            catalog_path=catalog_path,
            catalog_changed=changed,
            scanned_frame_count=len(metrics),
            trigger_frame_count=sum(bool(metric.candidate_labels) for metric in metrics),
            candidate_count=len(candidate_catalog.candidates),
            complete_candidate_count=sum(
                candidate.radar_collection.complete for candidate in candidate_catalog.candidates
            ),
            evidence_error_count=evidence_errors,
            cache_files_removed=removed_files,
            cache_bytes_removed=removed_bytes,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Incrementally discover CWA radar events and preserve reviewable evidence.",
    )
    parser.add_argument("--research-root", type=Path, default=None)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--initial-lookback-minutes", type=int, default=120)
    parser.add_argument("--merge-gap-minutes", type=int, default=60)
    parser.add_argument("--before-minutes", type=int, default=60)
    parser.add_argument("--after-minutes", type=int, default=60)
    parser.add_argument("--max-candidate-window-minutes", type=int, default=480)
    parser.add_argument("--evidence-max-alignment-minutes", type=int, default=20)
    parser.add_argument("--event-threshold-dbz", type=float, default=35.0)
    parser.add_argument("--local-radius-pixels", type=int, default=8)
    parser.add_argument("--local-min-pixels", type=int, default=1)
    parser.add_argument("--taiwan-min-pixels", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--cache-retention-hours", type=float, default=48.0)
    parser.add_argument("--cache-max-bytes", type=int, default=DEFAULT_CACHE_MAX_BYTES)
    parser.add_argument("--county-code", default="10010")
    parser.add_argument("--county-name", default="嘉義縣")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    started_at, start_timer = start_run()
    settings = get_settings()
    research_root = args.research_root or settings.research_root
    try:
        result = run_event_discovery(
            repository_root=args.repository_root,
            research_root=research_root,
            cwa_api_key=settings.cwa_api_key,
            wra_api_key=settings.wra_api_key,
            config=DiscoveryConfig(
                initial_lookback_minutes=args.initial_lookback_minutes,
                merge_gap_minutes=args.merge_gap_minutes,
                before_minutes=args.before_minutes,
                after_minutes=args.after_minutes,
                max_candidate_window_minutes=args.max_candidate_window_minutes,
                event_threshold_dbz=args.event_threshold_dbz,
                local_radius_pixels=args.local_radius_pixels,
                local_min_pixels=args.local_min_pixels,
                taiwan_min_pixels=args.taiwan_min_pixels,
                evidence_max_alignment_minutes=args.evidence_max_alignment_minutes,
            ),
            county_code=args.county_code,
            county_name=args.county_name,
            timeout=args.timeout,
            max_workers=args.max_workers,
            retry_attempts=args.retry_attempts,
            retry_backoff_seconds=args.retry_backoff_seconds,
            cache_retention_hours=args.cache_retention_hours,
            cache_max_bytes=args.cache_max_bytes,
        )
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=_safe_failure_reason(
                exc,
                secrets=(settings.cwa_api_key, settings.wra_api_key),
            ),
            started_at=started_at,
            start_timer=start_timer,
            inputs={"research_root": str(research_root)},
            metadata={"candidate_queue_only": True, "automatic_formal_split_updates": False},
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        LOGGER.exception("event discovery failed")
        raise SystemExit(1) from exc

    status = "needs_review" if result.evidence_error_count else "ok"
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status=status,
        failure_reason=(
            f"{result.evidence_error_count} synchronized evidence sources need retry"
            if result.evidence_error_count
            else ""
        ),
        started_at=started_at,
        start_timer=start_timer,
        inputs={"research_root": str(research_root), "radar_data_id": "O-A0059-001"},
        outputs={"event_evidence_catalog": str(result.catalog_path)},
        row_counts={
            "scanned_frames": result.scanned_frame_count,
            "trigger_frames": result.trigger_frame_count,
            "candidates": result.candidate_count,
            "complete_candidates": result.complete_candidate_count,
            "evidence_errors": result.evidence_error_count,
            "cache_files_removed": result.cache_files_removed,
            "cache_bytes_removed": result.cache_bytes_removed,
        },
        metadata={
            "catalog_changed": result.catalog_changed,
            "event_threshold_dbz": args.event_threshold_dbz,
            "max_candidate_window_minutes": args.max_candidate_window_minutes,
            "candidate_queue_only": True,
            "automatic_formal_split_updates": False,
            "human_review_required": True,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    LOGGER.info(
        "event discovery complete: scanned=%d triggers=%d candidates=%d catalog_changed=%s",
        result.scanned_frame_count,
        result.trigger_frame_count,
        result.candidate_count,
        result.catalog_changed,
    )


if __name__ == "__main__":
    main()
