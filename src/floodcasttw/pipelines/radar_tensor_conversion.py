"""Convert small radar-like CSV fixtures into model tensor archives."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.radar_tensor import RadarTensorSpec, validate_radar_tensor

PIPELINE_NAME = "radar_tensor_conversion"
DEFAULT_INPUT = Path("data/samples/radar_pixels.csv")
VALUE_FIELD = "mm_per_hour"
REQUIRED_FIELDS = {"event_id", "frame_index", "y", "x", VALUE_FIELD}


def read_pixel_records(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = REQUIRED_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing radar pixel fields: {', '.join(sorted(missing))}")
        return list(reader)


def select_event_id(records: list[dict[str, str]], event_id: str | None) -> str:
    event_ids = sorted({record["event_id"] for record in records})
    if not event_ids:
        raise ValueError("radar pixel CSV has no records")
    if event_id:
        if event_id not in event_ids:
            raise ValueError(f"event_id not found in radar pixel CSV: {event_id}")
        return event_id
    if len(event_ids) != 1:
        raise ValueError("radar pixel CSV has multiple events; pass --event-id")
    return event_ids[0]


def infer_size(records: list[dict[str, str]], field: str) -> int:
    return max(int(record[field]) for record in records) + 1


def build_sequence(
    records: list[dict[str, str]],
    *,
    event_id: str,
    spec: RadarTensorSpec,
) -> np.ndarray:
    sequence = np.full(
        (spec.total_length, spec.height, spec.width, spec.channels),
        np.nan,
        dtype=np.float32,
    )
    if spec.channels != 1:
        raise ValueError("CSV radar pixel conversion currently supports one channel")

    for record in records:
        if record["event_id"] != event_id:
            continue
        frame_index = int(record["frame_index"])
        y = int(record["y"])
        x = int(record["x"])
        if not (0 <= frame_index < spec.total_length):
            raise ValueError(f"frame_index out of bounds for {event_id}: {frame_index}")
        if not (0 <= y < spec.height and 0 <= x < spec.width):
            raise ValueError(f"grid coordinate out of bounds for {event_id}: y={y}, x={x}")
        if not np.isnan(sequence[frame_index, y, x, 0]):
            raise ValueError(f"duplicate pixel for {event_id}: frame={frame_index}, y={y}, x={x}")
        sequence[frame_index, y, x, 0] = float(record[VALUE_FIELD])

    missing = np.argwhere(np.isnan(sequence))
    if missing.size:
        first = missing[0].tolist()
        raise ValueError(f"missing radar pixel for {event_id}: index={first}")
    return sequence


def convert_records(
    records: list[dict[str, str]],
    *,
    event_id: str | None,
    input_length: int,
    prediction_length: int,
    height: int | None = None,
    width: int | None = None,
    cadence_minutes: int = 6,
    units: str = VALUE_FIELD,
    crs: str = "EPSG:4326",
) -> tuple[np.ndarray, np.ndarray, RadarTensorSpec, dict[str, object]]:
    selected_event_id = select_event_id(records, event_id)
    selected = [record for record in records if record["event_id"] == selected_event_id]
    spec = RadarTensorSpec(
        input_length=input_length,
        prediction_length=prediction_length,
        height=height or infer_size(selected, "y"),
        width=width or infer_size(selected, "x"),
        channels=1,
        cadence_minutes=cadence_minutes,
        units=units,
        crs=crs,
    )
    sequence = build_sequence(selected, event_id=selected_event_id, spec=spec)
    input_tensor = sequence[: spec.input_length]
    target_tensor = sequence[spec.input_length :]
    validate_radar_tensor(input_tensor, spec, kind="input")
    validate_radar_tensor(target_tensor, spec, kind="target")
    metadata = {
        "event_id": selected_event_id,
        "source_format": "csv_pixel_grid",
        "value_field": VALUE_FIELD,
        "frame_count": spec.total_length,
    }
    return input_tensor, target_tensor, spec, metadata


def write_tensor_archive(
    *,
    output_path: Path,
    input_tensor: np.ndarray,
    target_tensor: np.ndarray,
    spec: RadarTensorSpec,
    metadata: dict[str, object],
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        input=input_tensor,
        target=target_tensor,
        spec=json.dumps(spec.to_dict(), ensure_ascii=False),
        metadata=json.dumps(metadata, ensure_ascii=False),
    )


def load_tensor_archive(path: Path) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as archive:
        return {
            "input": archive["input"],
            "target": archive["target"],
            "spec": json.loads(str(archive["spec"].item())),
            "metadata": json.loads(str(archive["metadata"].item())),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert radar-like CSV pixels to tensor archive.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/radar_tensor_sample.npz"),
    )
    parser.add_argument("--event-id", default=None)
    parser.add_argument("--input-length", type=int, default=3)
    parser.add_argument("--prediction-length", type=int, default=2)
    parser.add_argument("--height", type=int, default=None)
    parser.add_argument("--width", type=int, default=None)
    parser.add_argument("--cadence-minutes", type=int, default=6)
    parser.add_argument("--units", default=VALUE_FIELD)
    parser.add_argument("--crs", default="EPSG:4326")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    records = read_pixel_records(args.input)
    input_tensor, target_tensor, spec, metadata = convert_records(
        records,
        event_id=args.event_id,
        input_length=args.input_length,
        prediction_length=args.prediction_length,
        height=args.height,
        width=args.width,
        cadence_minutes=args.cadence_minutes,
        units=args.units,
        crs=args.crs,
    )
    write_tensor_archive(
        output_path=args.output,
        input_tensor=input_tensor,
        target_tensor=target_tensor,
        spec=spec,
        metadata=metadata,
    )
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"radar_pixels": str(args.input)},
        outputs={"tensor_archive": str(args.output)},
        row_counts={"pixels": len(records), "frames": spec.total_length},
        metadata={
            "event_id": metadata["event_id"],
            "input_shape": list(input_tensor.shape),
            "target_shape": list(target_tensor.shape),
            "spec": spec.to_dict(),
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote radar tensor archive to {args.output}")


if __name__ == "__main__":
    main()
