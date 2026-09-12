"""History scanning, radar metrics, and candidate trigger helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from minxionghydrocast.ingestion.cwa_event_collector import CwaEventFrame, CwaEventPlan
from minxionghydrocast.ingestion.cwa_history import CwaHistoryFile, CwaHistoryIndex
from minxionghydrocast.io.research_store import sha256_file
from minxionghydrocast.models.event_evidence_schemas import (
    CandidateRadarCollection,
    CoverageMetric,
    DiscoveryConfig,
    DiscoveryCursor,
    EventCandidate,
    RadarFrameMetric,
    aware_datetime,
)
from minxionghydrocast.pipelines.radar_event_summary import EventFramePath, summarize_frame

from .event_discovery_catalog import iso_seconds


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


def scan_files(
    *,
    index: CwaHistoryIndex,
    cursor: DiscoveryCursor,
    config: DiscoveryConfig,
) -> tuple[CwaHistoryFile, ...]:
    files = unique_history_files(index)
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


def unique_history_files(index: CwaHistoryIndex) -> tuple[CwaHistoryFile, ...]:
    """Return one history record per timestamp in chronological order."""
    by_time: dict[datetime, CwaHistoryFile] = {}
    for item in index.files:
        if not item.data_time:
            continue
        parsed = aware_datetime(item.data_time, field="history data_time")
        by_time.setdefault(parsed, item)
    return tuple(by_time[key] for key in sorted(by_time))


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


def metric_from_frame(
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
        if (
            config.candidate_trigger_label not in metric.candidate_labels
            or metric.data_time in known_times
        ):
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
                and proposed_window <= timedelta(minutes=config.max_candidate_window_minutes)
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
