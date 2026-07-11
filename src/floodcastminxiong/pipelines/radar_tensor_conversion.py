"""Convert small radar-like CSV fixtures into model tensor archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from floodcastminxiong.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcastminxiong.models.radar_tensor import RadarTensorSpec, validate_radar_tensor
from floodcastminxiong.pipelines.radar_source_adapters import (
    CSV_PIXEL_GRID,
    CsvPixelGridAdapter,
    SUPPORTED_SOURCE_FORMATS,
    VALUE_FIELD,
    get_radar_source_adapter,
    read_csv_pixel_records,
)

PIPELINE_NAME = "radar_tensor_conversion"
DEFAULT_INPUT = Path("data/samples/radar_pixels.csv")
read_pixel_records = read_csv_pixel_records


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
    batch = CsvPixelGridAdapter().build_batch_from_records(
        records,
        event_id=event_id,
        input_length=input_length,
        prediction_length=prediction_length,
        height=height,
        width=width,
        cadence_minutes=cadence_minutes,
        units=units,
        crs=crs,
    )
    input_tensor = batch.sequence[: batch.spec.input_length]
    target_tensor = batch.sequence[batch.spec.input_length :]
    validate_radar_tensor(input_tensor, batch.spec, kind="input")
    validate_radar_tensor(target_tensor, batch.spec, kind="target")
    return input_tensor, target_tensor, batch.spec, batch.metadata


def convert_source(
    *,
    input_path: Path,
    source_format: str,
    event_id: str | None,
    input_length: int,
    prediction_length: int,
    height: int | None = None,
    width: int | None = None,
    cadence_minutes: int = 6,
    units: str = VALUE_FIELD,
    crs: str = "EPSG:4326",
    window_stride_frames: int = 0,
) -> tuple[np.ndarray, np.ndarray, RadarTensorSpec, dict[str, object], int]:
    if window_stride_frames < 0:
        raise ValueError("window_stride_frames must be zero or greater")
    adapter = get_radar_source_adapter(source_format)
    batch = adapter.load_sequence(
        input_path=input_path,
        event_id=event_id,
        input_length=input_length,
        prediction_length=prediction_length,
        height=height,
        width=width,
        cadence_minutes=cadence_minutes,
        units=units,
        crs=crs,
        load_all_frames=window_stride_frames > 0,
    )
    if window_stride_frames > 0:
        input_tensor, target_tensor, metadata = build_sliding_window_tensors(
            sequence=batch.sequence,
            spec=batch.spec,
            metadata=batch.metadata,
            window_stride_frames=window_stride_frames,
        )
    else:
        input_tensor = batch.sequence[: batch.spec.input_length]
        target_tensor = batch.sequence[batch.spec.input_length :]
        metadata = batch.metadata
        validate_radar_tensor(input_tensor, batch.spec, kind="input")
        validate_radar_tensor(target_tensor, batch.spec, kind="target")
    return input_tensor, target_tensor, batch.spec, metadata, batch.source_record_count


def build_sliding_window_tensors(
    *,
    sequence: np.ndarray,
    spec: RadarTensorSpec,
    metadata: dict[str, object],
    window_stride_frames: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    if window_stride_frames < 1:
        raise ValueError("window_stride_frames must be at least 1")
    sequence = np.asarray(sequence, dtype=np.float32)
    if sequence.ndim != 4:
        raise ValueError("source sequence must be [time, height, width, channels]")
    if sequence.shape[0] < spec.total_length:
        raise ValueError(
            f"source sequence has {sequence.shape[0]} frames; needs at least {spec.total_length}"
        )

    start_indices = list(
        range(0, sequence.shape[0] - spec.total_length + 1, window_stride_frames)
    )
    if not start_indices:
        raise ValueError("source sequence produced no sliding windows")
    inputs = np.stack(
        [
            sequence[start : start + spec.input_length]
            for start in start_indices
        ],
        axis=0,
    )
    targets = np.stack(
        [
            sequence[start + spec.input_length : start + spec.total_length]
            for start in start_indices
        ],
        axis=0,
    )
    validate_window_tensor(inputs, spec, kind="input")
    validate_window_tensor(targets, spec, kind="target")

    data_times = metadata.get("data_times", [])
    if isinstance(data_times, list):
        window_start_times = [str(data_times[index]) for index in start_indices]
        window_target_start_times = [
            str(data_times[index + spec.input_length]) for index in start_indices
        ]
    else:
        window_start_times = []
        window_target_start_times = []
    sliding_metadata = {
        **metadata,
        "archive_layout": "sliding_window",
        "source_frame_count": int(sequence.shape[0]),
        "window_count": len(start_indices),
        "window_stride_frames": window_stride_frames,
        "window_start_indices": start_indices,
        "window_start_times": window_start_times,
        "window_target_start_times": window_target_start_times,
        "target_lead_times_minutes": [
            spec.cadence_minutes * (index + 1)
            for index in range(spec.prediction_length)
        ],
    }
    return inputs, targets, sliding_metadata


def validate_window_tensor(array: np.ndarray, spec: RadarTensorSpec, *, kind: str) -> None:
    base_shape = spec.input_shape if kind == "input" else spec.target_shape
    expected_tail = base_shape
    actual = tuple(np.asarray(array).shape)
    if len(actual) != 5 or actual[1:] != expected_tail:
        raise ValueError(
            f"{kind} sliding-window radar tensor shape {actual} does not match "
            f"expected [sample, {', '.join(str(value) for value in expected_tail)}]"
        )


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
    parser.add_argument("--source-format", choices=SUPPORTED_SOURCE_FORMATS, default=CSV_PIXEL_GRID)
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
        "--window-stride-frames",
        type=int,
        default=0,
        help="When greater than zero, output sliding-window tensors with a sample axis.",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    input_tensor, target_tensor, spec, metadata, record_count = convert_source(
        input_path=args.input,
        source_format=args.source_format,
        event_id=args.event_id,
        input_length=args.input_length,
        prediction_length=args.prediction_length,
        height=args.height,
        width=args.width,
        cadence_minutes=args.cadence_minutes,
        units=args.units,
        crs=args.crs,
        window_stride_frames=args.window_stride_frames,
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
        row_counts={"source_records": record_count, "frames": spec.total_length},
        metadata={
            "event_id": metadata["event_id"],
            "source_format": args.source_format,
            "input_shape": list(input_tensor.shape),
            "target_shape": list(target_tensor.shape),
            "spec": spec.to_dict(),
            "archive_layout": metadata.get("archive_layout", "single_window"),
            "window_count": metadata.get("window_count", 1),
            "window_stride_frames": args.window_stride_frames,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote radar tensor archive to {args.output}")


if __name__ == "__main__":
    main()
