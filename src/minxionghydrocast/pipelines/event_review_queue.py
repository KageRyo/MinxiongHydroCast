"""Read-only priority report for human event-candidate review."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion.cwa_grid import extract_cwa_grid_values
from minxionghydrocast.io.research_store import ResearchLayout
from minxionghydrocast.models.dataset_schemas import ArtifactRecord
from minxionghydrocast.models.event_evidence_schemas import (
    EventCandidate,
    NormalizedSourceSnapshot,
)
from minxionghydrocast.pipelines.event_discovery import (
    artifact_matches,
    load_event_evidence_catalog,
    now_taipei,
)
from minxionghydrocast.pipelines.radar_event_summary import (
    grid_xy_for_lon_lat,
    valid_value_mask,
)

PRIORITY_POLICY = (
    "artifact-complete candidates with synchronized evidence first",
    "Minxiong-local triggers before retained Taiwan-wide-only context",
    "active warnings, Minxiong gauge peak, local QPE, and local radar peak descending",
    "local trigger count descending, then oldest trigger first",
)


class ReviewQueueSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class EvidenceStatusSummary(ReviewQueueSchema):
    capture_count: int = Field(ge=0)
    status_counts: dict[str, int]


class QpeQueueSummary(EvidenceStatusSummary):
    local_point_peak_mm: float | None = Field(default=None, ge=0)


class GaugeQueueSummary(EvidenceStatusSummary):
    minxiong_station_count: int = Field(ge=0)
    minxiong_one_hour_peak_mm: float | None = Field(default=None, ge=0)


class WarningQueueSummary(EvidenceStatusSummary):
    active_capture_count: int = Field(ge=0)
    max_warning_record_count: int = Field(ge=0)


class ArtifactQueueSummary(ReviewQueueSchema):
    expected_count: int = Field(ge=0)
    verified_count: int = Field(ge=0)
    complete: bool
    data_errors: list[str]


class EventReviewQueueItem(ReviewQueueSchema):
    rank: int = Field(ge=1)
    candidate_id: str
    review_status: Literal["pending", "approved", "rejected"]
    operational_status: Literal["collecting", "awaiting_review", "incomplete"]
    first_trigger_time: str
    last_trigger_time: str
    local_peak_dbz: float | None
    trigger_count: int = Field(ge=1)
    local_trigger_count: int = Field(ge=0)
    radar_expected_frames: int = Field(ge=1)
    radar_captured_frames: int = Field(ge=0)
    radar_complete: bool
    synchronized_capture_count: int = Field(ge=0)
    qpe: QpeQueueSummary
    gauges: GaugeQueueSummary
    warnings: WarningQueueSummary
    official_context_count: int = Field(ge=0)
    artifacts: ArtifactQueueSummary
    review_ready: bool
    formal_split_membership: Literal["not_added"]


class EventReviewQueueReport(ReviewQueueSchema):
    schema_version: Literal[1] = 1
    generated_at: str
    catalog_path: str
    catalog_updated_at: str
    pending_only: bool
    automatic_formal_split_updates: Literal[False] = False
    candidate_count: int = Field(ge=0)
    priority_policy: tuple[str, ...] = PRIORITY_POLICY
    candidates: list[EventReviewQueueItem]


def _status_summary(candidate: EventCandidate, source_name: str) -> EvidenceStatusSummary:
    statuses = Counter(
        getattr(capture, source_name).status
        for capture in candidate.evidence_captures
    )
    return EvidenceStatusSummary(
        capture_count=len(candidate.evidence_captures),
        status_counts=dict(sorted(statuses.items())),
    )


def _candidate_artifacts(candidate: EventCandidate) -> list[ArtifactRecord]:
    collection = candidate.radar_collection
    artifacts = [
        artifact
        for artifact in (collection.plan, collection.collection)
        if artifact is not None
    ]
    artifacts.extend(collection.frames)
    for capture in candidate.evidence_captures:
        artifacts.extend(
            source.artifact
            for source in (capture.qpe, capture.gauges, capture.warnings)
            if source.artifact is not None
        )
    if candidate.review is not None:
        artifacts.extend(
            context.artifact
            for context in candidate.review.official_context_artifacts
        )
    return artifacts


def _qpe_local_value(
    path: Path,
    *,
    longitude: float,
    latitude: float,
) -> float | None:
    inspection, values = extract_cwa_grid_values(path)
    grid = np.asarray(values, dtype=np.float32).reshape(
        inspection.grid_dimension_y,
        inspection.grid_dimension_x,
    )
    x, y = grid_xy_for_lon_lat(
        inspection,
        longitude=longitude,
        latitude=latitude,
    )
    value = grid[y, x]
    if not valid_value_mask(
        np.asarray([value], dtype=np.float32),
        inspection.nodata_values,
    )[0]:
        return None
    return round(float(value), 3)


def _normalized_snapshot(path: Path) -> NormalizedSourceSnapshot:
    return NormalizedSourceSnapshot.model_validate_json(
        path.read_text(encoding="utf-8")
    )


def _evidence_summaries(
    candidate: EventCandidate,
    *,
    layout: ResearchLayout,
    longitude: float,
    latitude: float,
) -> tuple[
    QpeQueueSummary,
    GaugeQueueSummary,
    WarningQueueSummary,
    list[str],
]:
    qpe_status = _status_summary(candidate, "qpe")
    gauge_status = _status_summary(candidate, "gauges")
    warning_status = _status_summary(candidate, "warnings")
    qpe_values: list[float] = []
    gauge_peaks: list[float] = []
    station_counts: list[int] = []
    active_warning_counts: list[int] = []
    errors: list[str] = []

    for capture in candidate.evidence_captures:
        qpe_artifact = capture.qpe.artifact
        if qpe_artifact is not None:
            try:
                value = _qpe_local_value(
                    layout.resolve_relative(qpe_artifact.path),
                    longitude=longitude,
                    latitude=latitude,
                )
                if value is not None:
                    qpe_values.append(value)
            except Exception as exc:
                errors.append(f"{qpe_artifact.path}: {type(exc).__name__}")

        gauge_artifact = capture.gauges.artifact
        if gauge_artifact is not None:
            try:
                snapshot = _normalized_snapshot(
                    layout.resolve_relative(gauge_artifact.path)
                )
                minxiong_records = [
                    record
                    for record in snapshot.records
                    if record.get("行政區", "").endswith("民雄鄉")
                ]
                station_counts.append(
                    len(
                        {
                            record.get("雨量站代碼") or record.get("雨量站")
                            for record in minxiong_records
                        }
                    )
                )
                gauge_peaks.extend(
                    float(record["1小時累積雨量mm"])
                    for record in minxiong_records
                    if record.get("1小時累積雨量mm", "").strip()
                )
            except Exception as exc:
                errors.append(f"{gauge_artifact.path}: {type(exc).__name__}")

        warning_artifact = capture.warnings.artifact
        if warning_artifact is not None:
            try:
                snapshot = _normalized_snapshot(
                    layout.resolve_relative(warning_artifact.path)
                )
                active_warning_counts.append(len(snapshot.records))
            except Exception as exc:
                errors.append(f"{warning_artifact.path}: {type(exc).__name__}")

    return (
        QpeQueueSummary(
            **qpe_status.model_dump(),
            local_point_peak_mm=max(qpe_values, default=None),
        ),
        GaugeQueueSummary(
            **gauge_status.model_dump(),
            minxiong_station_count=max(station_counts, default=0),
            minxiong_one_hour_peak_mm=max(gauge_peaks, default=None),
        ),
        WarningQueueSummary(
            **warning_status.model_dump(),
            active_capture_count=sum(count > 0 for count in active_warning_counts),
            max_warning_record_count=max(active_warning_counts, default=0),
        ),
        errors,
    )


def _queue_item(
    candidate: EventCandidate,
    *,
    layout: ResearchLayout,
    longitude: float,
    latitude: float,
) -> EventReviewQueueItem:
    qpe, gauges, warnings, data_errors = _evidence_summaries(
        candidate,
        layout=layout,
        longitude=longitude,
        latitude=latitude,
    )
    artifacts = _candidate_artifacts(candidate)
    verified_count = sum(artifact_matches(layout, artifact) for artifact in artifacts)
    artifact_complete = (
        candidate.radar_collection.complete
        and verified_count == len(artifacts)
        and not data_errors
    )
    synchronized_capture_count = sum(
        capture.qpe.status == "ok"
        and capture.gauges.status == "ok"
        and capture.warnings.status in {"ok", "empty"}
        for capture in candidate.evidence_captures
    )
    local_peak_values = [
        trigger.local.max_value
        for trigger in candidate.triggers
        if trigger.local.max_value is not None
    ]
    local_trigger_count = sum(
        "minxiong_35dbz" in trigger.candidate_labels
        for trigger in candidate.triggers
    )
    official_context_count = (
        len(candidate.review.official_context_artifacts)
        if candidate.review is not None
        else 0
    )
    return EventReviewQueueItem(
        rank=1,
        candidate_id=candidate.candidate_id,
        review_status=candidate.review_status,
        operational_status=candidate.operational_status,
        first_trigger_time=candidate.first_trigger_time,
        last_trigger_time=candidate.last_trigger_time,
        local_peak_dbz=max(local_peak_values, default=None),
        trigger_count=len(candidate.triggers),
        local_trigger_count=local_trigger_count,
        radar_expected_frames=candidate.radar_collection.expected_frame_count,
        radar_captured_frames=candidate.radar_collection.captured_frame_count,
        radar_complete=candidate.radar_collection.complete,
        synchronized_capture_count=synchronized_capture_count,
        qpe=qpe,
        gauges=gauges,
        warnings=warnings,
        official_context_count=official_context_count,
        artifacts=ArtifactQueueSummary(
            expected_count=len(artifacts),
            verified_count=verified_count,
            complete=artifact_complete,
            data_errors=data_errors,
        ),
        review_ready=(
            candidate.review_status == "pending"
            and artifact_complete
            and synchronized_capture_count > 0
        ),
        formal_split_membership=candidate.formal_split_membership,
    )


def _descending(value: float | None) -> float:
    return -(value if value is not None else -1.0)


def _priority_key(item: EventReviewQueueItem) -> tuple[object, ...]:
    return (
        not item.review_ready,
        item.local_trigger_count == 0,
        -item.warnings.active_capture_count,
        _descending(item.gauges.minxiong_one_hour_peak_mm),
        _descending(item.qpe.local_point_peak_mm),
        _descending(item.local_peak_dbz),
        -item.local_trigger_count,
        item.first_trigger_time,
        item.candidate_id,
    )


def build_event_review_queue(
    *,
    catalog_path: Path,
    pending_only: bool = True,
    now: datetime | None = None,
) -> EventReviewQueueReport:
    """Build a report without writing the catalog, evidence, or formal split."""

    catalog = load_event_evidence_catalog(catalog_path)
    layout = ResearchLayout(Path(catalog.research_root))
    candidates = [
        candidate
        for candidate in catalog.candidates
        if not pending_only or candidate.review_status == "pending"
    ]
    items = [
        _queue_item(
            candidate,
            layout=layout,
            longitude=catalog.config.local_longitude,
            latitude=catalog.config.local_latitude,
        )
        for candidate in candidates
    ]
    ranked = [
        item.model_copy(update={"rank": rank})
        for rank, item in enumerate(sorted(items, key=_priority_key), start=1)
    ]
    generated_at = (now or now_taipei()).isoformat(timespec="seconds")
    return EventReviewQueueReport(
        generated_at=generated_at,
        catalog_path=str(catalog_path),
        catalog_updated_at=catalog.updated_at,
        pending_only=pending_only,
        candidate_count=len(ranked),
        candidates=ranked,
    )


def _status_text(summary: EvidenceStatusSummary) -> str:
    return ",".join(
        f"{status}:{count}"
        for status, count in sorted(summary.status_counts.items())
    ) or "-"


def render_event_review_queue_table(report: EventReviewQueueReport) -> str:
    headings = (
        "rank",
        "candidate",
        "local_dBZ",
        "triggers",
        "QPE_mm/status",
        "gauge_mm/stations/status",
        "warnings_active/status",
        "context",
        "artifacts",
        "ready",
    )
    rows = ["\t".join(headings)]
    for item in report.candidates:
        rows.append(
            "\t".join(
                (
                    str(item.rank),
                    item.candidate_id,
                    (
                        f"{item.local_peak_dbz:.1f}"
                        if item.local_peak_dbz is not None
                        else "-"
                    ),
                    f"{item.local_trigger_count}/{item.trigger_count}",
                    (
                        f"{item.qpe.local_point_peak_mm:.1f}"
                        if item.qpe.local_point_peak_mm is not None
                        else "-"
                    )
                    + f"/{_status_text(item.qpe)}",
                    (
                        f"{item.gauges.minxiong_one_hour_peak_mm:.1f}"
                        if item.gauges.minxiong_one_hour_peak_mm is not None
                        else "-"
                    )
                    + (
                        f"/{item.gauges.minxiong_station_count}"
                        f"/{_status_text(item.gauges)}"
                    ),
                    (
                        f"{item.warnings.active_capture_count}"
                        f"/{_status_text(item.warnings)}"
                    ),
                    str(item.official_context_count),
                    (
                        f"{item.artifacts.verified_count}/"
                        f"{item.artifacts.expected_count}"
                    ),
                    "yes" if item.review_ready else "no",
                )
            )
        )
    return "\n".join(rows)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=(
            "Print a read-only priority report for event candidates; never edits "
            "the catalog or formal split."
        ),
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=settings.research_root / "discovery" / "event_evidence_catalog.json",
    )
    parser.add_argument(
        "--include-reviewed",
        action="store_true",
        help="Include approved and rejected candidates after pending candidates.",
    )
    parser.add_argument("--format", choices=("table", "json"), default="table")
    args = parser.parse_args()

    report = build_event_review_queue(
        catalog_path=args.catalog,
        pending_only=not args.include_reviewed,
    )
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(render_event_review_queue_table(report))


if __name__ == "__main__":
    main()
