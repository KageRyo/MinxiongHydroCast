"""Evidence collection and candidate artifact refresh helpers."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from minxionghydrocast.ingestion.cwa_event_collector import (
    CwaCollectedFrame,
    CwaEventCollection,
    CwaEventFrame,
    CwaEventPlan,
    build_event_plan,
    download_event_frames,
    load_event_collection,
)
from minxionghydrocast.ingestion.cwa_file_api import CwaDownloadRequest, download_cwa_file
from minxionghydrocast.ingestion.cwa_grid import inspect_cwa_grid_file
from minxionghydrocast.ingestion.cwa_history import CwaHistoryIndex
from minxionghydrocast.ingestion.source_adapter import SourceAdapterError, SourceResult
from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    sha256_file,
    write_schema_if_changed,
)
from minxionghydrocast.models.dataset_schemas import ArtifactRecord
from minxionghydrocast.models.event_evidence_schemas import (
    CandidateRadarCollection,
    DiscoveryConfig,
    EventCandidate,
    EvidenceSourceRecord,
    NormalizedSourceSnapshot,
    SynchronizedEvidenceCapture,
    aware_datetime,
)

from .event_discovery_catalog import artifact_matches, iso_seconds
from .event_discovery_metrics import expected_data_times
from .event_discovery_types import FileHttpGet, FrameHttpGet


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
    # DiscoveryConfig is kept as an object here to avoid exposing orchestration details in
    # this evidence module; the fields used below are validated by the caller's model.
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
    capture_id = (
        f"{candidate.candidate_id}_{aware_datetime(target, field='target'):%Y%m%dt%H%M}"
    )
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
