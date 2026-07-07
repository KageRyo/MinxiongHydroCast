"""Evaluate baselines directly on radar tensor archives."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.baselines import PersistenceNowcaster
from floodcasttw.models.metrics import binary_event_metrics, rmse
from floodcasttw.models.radar_tensor import nodata_values_from_metadata, valid_value_mask
from floodcasttw.pipelines.radar_tensor_conversion import load_tensor_archive

PIPELINE_NAME = "tensor_baseline_evaluation"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def evaluate_persistence_tensor_archive(
    *,
    archive_path: Path,
    event_threshold_mm: float = 10.0,
) -> dict[str, object]:
    archive = load_tensor_archive(archive_path)
    input_tensor = np.asarray(archive["input"], dtype=np.float32)
    target_tensor = np.asarray(archive["target"], dtype=np.float32)
    metadata = archive["metadata"]
    spec = archive["spec"]
    value_units = str(spec.get("units", ""))
    nodata_values = nodata_values_from_metadata(metadata)
    model = PersistenceNowcaster(horizon=target_tensor.shape[0])
    prediction = model.predict(input_tensor)
    target_mask = valid_value_mask(target_tensor, nodata_values)
    latest_input_mask = valid_value_mask(input_tensor[-1:], nodata_values)
    prediction_mask = np.repeat(latest_input_mask, target_tensor.shape[0], axis=0)
    evaluation_mask = target_mask & prediction_mask
    valid_pixels = int(evaluation_mask.sum())
    ignored_pixels = int(evaluation_mask.size - valid_pixels)
    if valid_pixels == 0:
        raise ValueError("tensor archive has no valid pixels for evaluation")
    prediction_valid = prediction[evaluation_mask]
    target_valid = target_tensor[evaluation_mask]
    event_metrics = binary_event_metrics(
        prediction_valid >= event_threshold_mm,
        target_valid >= event_threshold_mm,
    )
    rmse_value = round(rmse(prediction_valid, target_valid), 6)
    return {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "model": "PersistenceNowcaster",
        "archive": str(archive_path),
        "event_id": metadata.get("event_id", ""),
        "horizon": int(target_tensor.shape[0]),
        "input_shape": list(input_tensor.shape),
        "target_shape": list(target_tensor.shape),
        "prediction_shape": list(prediction.shape),
        "rmse_mm": rmse_value,
        "rmse": rmse_value,
        "value_units": value_units,
        "rmse_units": value_units,
        "event_threshold_mm": event_threshold_mm,
        "event_threshold": event_threshold_mm,
        "event_threshold_units": value_units,
        "event_metrics": event_metrics.to_dict(),
        "valid_pixel_count": valid_pixels,
        "ignored_pixel_count": ignored_pixels,
        "nodata_values": list(nodata_values),
        "tensor_spec": spec,
        "metadata": metadata,
    }


def write_evaluation_result(result: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baselines on a radar tensor archive.")
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/processed/radar_tensor_sample.npz"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/tensor_baseline_evaluation.json"),
    )
    parser.add_argument("--event-threshold-mm", type=float, default=10.0)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    result = evaluate_persistence_tensor_archive(
        archive_path=args.archive,
        event_threshold_mm=args.event_threshold_mm,
    )
    write_evaluation_result(result, args.output)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"archive": str(args.archive)},
        outputs={"evaluation": str(args.output)},
        row_counts={"input_frames": result["input_shape"][0], "target_frames": result["horizon"]},
        metrics={
            "rmse_mm": result["rmse_mm"],
            "csi": result["event_metrics"]["csi"],
            "pod": result["event_metrics"]["pod"],
            "far": result["event_metrics"]["far"],
        },
        metadata={
            "event_id": result["event_id"],
            "event_threshold_mm": args.event_threshold_mm,
            "valid_pixel_count": result["valid_pixel_count"],
            "ignored_pixel_count": result["ignored_pixel_count"],
            "nodata_values": result["nodata_values"],
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote tensor baseline evaluation to {args.output}")


if __name__ == "__main__":
    main()
