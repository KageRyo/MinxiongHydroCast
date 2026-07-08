"""Summarize CWA radar event windows for dataset selection."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from floodcasttw.ingestion.cwa_grid import (
    CwaGridInspection,
    check_cwa_grid_sequence,
    extract_cwa_grid_values,
    parse_iso_datetime,
)
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "radar_event_summary"
DEFAULT_LOCAL_LON = 120.43
DEFAULT_LOCAL_LAT = 23.55


@dataclass(frozen=True)
class EventFramePath:
    data_time: str
    path: Path


def load_collection_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("event collection manifest must be a JSON object")
    return payload


def collection_frame_paths(manifest: dict[str, Any]) -> list[EventFramePath]:
    frames = []
    for item in manifest.get("frames", []):
        if not isinstance(item, dict):
            continue
        output_path = str(item.get("output_path", ""))
        data_time = str(item.get("data_time", ""))
        if output_path and data_time:
            frames.append(EventFramePath(data_time=data_time, path=Path(output_path)))
    frames.sort(key=lambda frame: parse_iso_datetime(frame.data_time))
    return frames


def valid_value_mask(values: np.ndarray, nodata_values: tuple[float, ...]) -> np.ndarray:
    mask = np.isfinite(values)
    for nodata_value in nodata_values:
        mask &= ~np.isclose(values, nodata_value)
    return mask


def grid_xy_for_lon_lat(
    inspection: CwaGridInspection,
    *,
    longitude: float,
    latitude: float,
) -> tuple[int, int]:
    x = int(round((longitude - inspection.start_longitude) / inspection.grid_resolution))
    y = int(round((latitude - inspection.start_latitude) / inspection.grid_resolution))
    if x < 0 or x >= inspection.grid_dimension_x or y < 0 or y >= inspection.grid_dimension_y:
        raise ValueError(
            "local focus coordinate falls outside CWA grid: "
            f"lon={longitude}, lat={latitude}, x={x}, y={y}"
        )
    return x, y


def finite_max(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    return float(np.max(values))


def finite_mean(values: np.ndarray) -> float | None:
    if values.size == 0:
        return None
    return float(np.mean(values))


def summarize_frame(
    frame: EventFramePath,
    *,
    local_longitude: float,
    local_latitude: float,
    local_radius_pixels: int,
    event_threshold: float,
) -> tuple[dict[str, object], CwaGridInspection]:
    inspection, values = extract_cwa_grid_values(frame.path)
    grid = np.asarray(values, dtype=np.float32).reshape(
        inspection.grid_dimension_y,
        inspection.grid_dimension_x,
    )
    valid_mask = valid_value_mask(grid, inspection.nodata_values)
    valid_values = grid[valid_mask]

    x, y = grid_xy_for_lon_lat(
        inspection,
        longitude=local_longitude,
        latitude=local_latitude,
    )
    y0 = max(0, y - local_radius_pixels)
    y1 = min(inspection.grid_dimension_y, y + local_radius_pixels + 1)
    x0 = max(0, x - local_radius_pixels)
    x1 = min(inspection.grid_dimension_x, x + local_radius_pixels + 1)
    local_grid = grid[y0:y1, x0:x1]
    local_mask = valid_mask[y0:y1, x0:x1]
    local_values = local_grid[local_mask]

    threshold_mask = valid_values >= event_threshold
    local_threshold_mask = local_values >= event_threshold
    valid_count = int(valid_values.size)
    local_valid_count = int(local_values.size)
    total_pixel_count = inspection.grid_dimension_x * inspection.grid_dimension_y

    summary = {
        "data_time": inspection.data_time,
        "path": str(frame.path),
        "grid": {
            "data_id": inspection.data_id,
            "units": inspection.units,
            "height": inspection.grid_dimension_y,
            "width": inspection.grid_dimension_x,
            "total_pixel_count": total_pixel_count,
            "valid_pixel_count": valid_count,
            "valid_pixel_fraction": round(valid_count / total_pixel_count, 6)
            if total_pixel_count
            else 0.0,
        },
        "taiwan_wide": {
            "max_value": finite_max(valid_values),
            "mean_value": finite_mean(valid_values),
            "pixels_ge_threshold": int(np.count_nonzero(threshold_mask)),
            "fraction_ge_threshold": round(float(np.mean(threshold_mask)), 6)
            if valid_count
            else 0.0,
        },
        "local_focus": {
            "center_x": x,
            "center_y": y,
            "radius_pixels": local_radius_pixels,
            "valid_pixel_count": local_valid_count,
            "max_value": finite_max(local_values),
            "mean_value": finite_mean(local_values),
            "pixels_ge_threshold": int(np.count_nonzero(local_threshold_mask)),
            "fraction_ge_threshold": round(float(np.mean(local_threshold_mask)), 6)
            if local_valid_count
            else 0.0,
        },
    }
    return summary, inspection


def _peak_frame(frames: list[dict[str, object]], section: str) -> dict[str, object] | None:
    candidates = []
    for frame in frames:
        section_payload = frame.get(section, {})
        if not isinstance(section_payload, dict):
            continue
        value = section_payload.get("max_value")
        if value is not None:
            candidates.append(frame)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda frame: float((frame[section]).get("max_value", float("-inf"))),  # type: ignore[index]
    )


def _coverage_peak_frame(
    frames: list[dict[str, object]],
    section: str,
) -> dict[str, object] | None:
    candidates = []
    for frame in frames:
        section_payload = frame.get(section, {})
        if not isinstance(section_payload, dict):
            continue
        if int(section_payload.get("pixels_ge_threshold", 0)) > 0:
            candidates.append(frame)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda frame: (
            int((frame[section]).get("pixels_ge_threshold", 0)),  # type: ignore[index]
            float((frame[section]).get("max_value") or float("-inf")),  # type: ignore[index]
        ),
    )


def summarize_event_collection(
    collection_manifest_path: Path,
    *,
    local_name: str = "Minxiong, Chiayi County",
    local_longitude: float = DEFAULT_LOCAL_LON,
    local_latitude: float = DEFAULT_LOCAL_LAT,
    local_radius_pixels: int = 8,
    event_threshold: float = 35.0,
    expected_cadence_minutes: int = 10,
) -> dict[str, object]:
    manifest = load_collection_manifest(collection_manifest_path)
    frame_paths = collection_frame_paths(manifest)
    if not frame_paths:
        raise ValueError("event collection manifest has no local frame paths")

    frame_summaries = []
    inspections = []
    for frame in frame_paths:
        frame_summary, inspection = summarize_frame(
            frame,
            local_longitude=local_longitude,
            local_latitude=local_latitude,
            local_radius_pixels=local_radius_pixels,
            event_threshold=event_threshold,
        )
        frame_summaries.append(frame_summary)
        inspections.append(inspection)

    sequence_check = check_cwa_grid_sequence(
        inspections,
        expected_cadence_minutes=expected_cadence_minutes,
    )
    local_peak = _peak_frame(frame_summaries, "local_focus")
    taiwan_peak = _peak_frame(frame_summaries, "taiwan_wide")
    local_coverage_peak = _coverage_peak_frame(frame_summaries, "local_focus")
    taiwan_coverage_peak = _coverage_peak_frame(frame_summaries, "taiwan_wide")

    local_frames_over_threshold = [
        frame
        for frame in frame_summaries
        if int((frame["local_focus"]).get("pixels_ge_threshold", 0)) > 0  # type: ignore[index]
    ]
    taiwan_frames_over_threshold = [
        frame
        for frame in frame_summaries
        if int((frame["taiwan_wide"]).get("pixels_ge_threshold", 0)) > 0  # type: ignore[index]
    ]
    labels = []
    if local_frames_over_threshold:
        labels.append("chiayi_minxiong_heavy_rain_radar_candidate")
    if taiwan_frames_over_threshold:
        labels.append("taiwan_wide_widespread_radar_candidate")

    return {
        "schema_version": "1.0",
        "event_id": str(manifest.get("event_id", collection_manifest_path.stem)),
        "data_id": str(manifest.get("data_id", "")),
        "source_collection": str(collection_manifest_path),
        "frame_count": len(frame_summaries),
        "start_time": str(frame_summaries[0]["data_time"]),
        "end_time": str(frame_summaries[-1]["data_time"]),
        "event_threshold": event_threshold,
        "event_threshold_units": inspections[0].units,
        "candidate_labels": labels,
        "synoptic_label_status": "radar_only_pending_official_weather_context",
        "local_focus": {
            "name": local_name,
            "longitude": local_longitude,
            "latitude": local_latitude,
            "radius_pixels": local_radius_pixels,
            "frames_over_threshold": len(local_frames_over_threshold),
            "peak_time": str(local_peak["data_time"]) if local_peak else "",
            "peak_max_value": (
                (local_peak["local_focus"]).get("max_value") if local_peak else None  # type: ignore[index]
            ),
            "coverage_peak_time": str(local_coverage_peak["data_time"])
            if local_coverage_peak
            else "",
            "coverage_peak_pixels_ge_threshold": (
                (local_coverage_peak["local_focus"]).get("pixels_ge_threshold")
                if local_coverage_peak
                else None
            ),
            "coverage_peak_fraction_ge_threshold": (
                (local_coverage_peak["local_focus"]).get("fraction_ge_threshold")
                if local_coverage_peak
                else None
            ),
            "total_pixels_ge_threshold": sum(
                int((frame["local_focus"]).get("pixels_ge_threshold", 0))  # type: ignore[index]
                for frame in frame_summaries
            ),
        },
        "taiwan_wide": {
            "frames_over_threshold": len(taiwan_frames_over_threshold),
            "peak_time": str(taiwan_peak["data_time"]) if taiwan_peak else "",
            "peak_max_value": (
                (taiwan_peak["taiwan_wide"]).get("max_value") if taiwan_peak else None  # type: ignore[index]
            ),
            "peak_pixels_ge_threshold": (
                (taiwan_peak["taiwan_wide"]).get("pixels_ge_threshold")
                if taiwan_peak
                else None
            ),
            "coverage_peak_time": str(taiwan_coverage_peak["data_time"])
            if taiwan_coverage_peak
            else "",
            "coverage_peak_max_value": (
                (taiwan_coverage_peak["taiwan_wide"]).get("max_value")
                if taiwan_coverage_peak
                else None
            ),
            "coverage_peak_pixels_ge_threshold": (
                (taiwan_coverage_peak["taiwan_wide"]).get("pixels_ge_threshold")
                if taiwan_coverage_peak
                else None
            ),
            "coverage_peak_fraction_ge_threshold": (
                (taiwan_coverage_peak["taiwan_wide"]).get("fraction_ge_threshold")
                if taiwan_coverage_peak
                else None
            ),
            "total_pixels_ge_threshold": sum(
                int((frame["taiwan_wide"]).get("pixels_ge_threshold", 0))  # type: ignore[index]
                for frame in frame_summaries
            ),
        },
        "sequence_check": sequence_check,
        "frames": frame_summaries,
    }


def write_event_summary(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a CWA radar event collection.")
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("data/processed/radar_event_summary.json"))
    parser.add_argument("--local-name", default="Minxiong, Chiayi County")
    parser.add_argument("--local-longitude", type=float, default=DEFAULT_LOCAL_LON)
    parser.add_argument("--local-latitude", type=float, default=DEFAULT_LOCAL_LAT)
    parser.add_argument("--local-radius-pixels", type=int, default=8)
    parser.add_argument("--event-threshold", type=float, default=35.0)
    parser.add_argument("--expected-cadence-minutes", type=int, default=10)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    summary = summarize_event_collection(
        args.collection,
        local_name=args.local_name,
        local_longitude=args.local_longitude,
        local_latitude=args.local_latitude,
        local_radius_pixels=args.local_radius_pixels,
        event_threshold=args.event_threshold,
        expected_cadence_minutes=args.expected_cadence_minutes,
    )
    write_event_summary(args.output, summary)

    local_focus = summary["local_focus"]
    taiwan_wide = summary["taiwan_wide"]
    run_summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok" if summary["sequence_check"]["status"] == "ok" else "needs_review",  # type: ignore[index]
        failure_reason="; ".join(summary["sequence_check"].get("errors", [])),  # type: ignore[union-attr]
        started_at=started_at,
        start_timer=start_timer,
        inputs={"collection": str(args.collection)},
        outputs={"event_summary": str(args.output)},
        row_counts={"frames": summary["frame_count"]},
        metrics={
            "local_frames_over_threshold": local_focus["frames_over_threshold"],  # type: ignore[index]
            "taiwan_frames_over_threshold": taiwan_wide["frames_over_threshold"],  # type: ignore[index]
            "local_peak_max_value": local_focus["peak_max_value"],  # type: ignore[index]
            "taiwan_peak_max_value": taiwan_wide["peak_max_value"],  # type: ignore[index]
        },
        metadata={
            "event_id": summary["event_id"],
            "event_threshold": args.event_threshold,
            "event_threshold_units": summary["event_threshold_units"],
            "candidate_labels": summary["candidate_labels"],
            "synoptic_label_status": summary["synoptic_label_status"],
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=run_summary)
    print(f"[OK] Wrote radar event summary to {args.output}")


if __name__ == "__main__":
    main()
