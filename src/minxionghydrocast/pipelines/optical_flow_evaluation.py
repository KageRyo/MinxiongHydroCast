"""Evaluate the deterministic CPU optical-flow baseline on radar tensors."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.baselines import OpticalFlowNowcaster
from minxionghydrocast.models.evaluation_schemas import OpticalFlowComparisonSchema
from minxionghydrocast.models.metrics import mae
from minxionghydrocast.models.radar_tensor import nodata_values_from_metadata, valid_value_mask
from minxionghydrocast.pipelines.radar_tensor_conversion import load_tensor_archive
from minxionghydrocast.pipelines.tensor_baseline_evaluation import (
    common_evaluation_mask,
    evaluate_masked_arrays,
    persistence_predict,
)

PIPELINE_NAME = "optical_flow_evaluation"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def evaluate_masked_arrays_with_mae(
    *,
    prediction: np.ndarray,
    target: np.ndarray,
    evaluation_mask: np.ndarray,
    event_threshold: float,
) -> dict[str, object]:
    """Evaluate continuous and threshold metrics on one common valid-pixel mask."""

    metrics = evaluate_masked_arrays(
        prediction=prediction,
        target=target,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
    )
    prediction_valid = prediction[evaluation_mask]
    target_valid = target[evaluation_mask]
    metrics["mae"] = round(mae(prediction_valid, target_valid), 6)
    return metrics


def lead_time_breakdown_with_mae(
    *,
    prediction: np.ndarray,
    target: np.ndarray,
    evaluation_mask: np.ndarray,
    event_threshold: float,
    cadence_minutes: int,
) -> list[dict[str, object]]:
    """Return RMSE, MAE, and event metrics for every forecast lead time."""

    lead_axis = 0 if target.ndim == 4 else 1
    lead_count = target.shape[lead_axis]
    results = []
    for lead_index in range(lead_count):
        if target.ndim == 4:
            lead_prediction = prediction[lead_index : lead_index + 1]
            lead_target = target[lead_index : lead_index + 1]
            lead_mask = evaluation_mask[lead_index : lead_index + 1]
        else:
            lead_prediction = prediction[:, lead_index : lead_index + 1]
            lead_target = target[:, lead_index : lead_index + 1]
            lead_mask = evaluation_mask[:, lead_index : lead_index + 1]
        metrics = evaluate_masked_arrays_with_mae(
            prediction=lead_prediction,
            target=lead_target,
            evaluation_mask=lead_mask,
            event_threshold=event_threshold,
        )
        results.append(
            {
                "lead_index": lead_index,
                "lead_time_minutes": cadence_minutes * (lead_index + 1),
                **metrics,
            }
        )
    return results


def optical_flow_predict(
    input_tensor: np.ndarray,
    *,
    horizon: int,
    input_mask: np.ndarray,
    max_displacement: int | None,
    min_valid_pixels: int,
    fill_value: float,
) -> np.ndarray:
    """Predict either a single sequence or each independent sliding-window sample."""

    nowcaster = OpticalFlowNowcaster(
        horizon=horizon,
        max_displacement=max_displacement,
        min_valid_pixels=min_valid_pixels,
        fill_value=fill_value,
    )
    if input_tensor.ndim == 4:
        return nowcaster.predict(input_tensor, valid_mask=input_mask)
    if input_tensor.ndim == 5:
        return np.stack(
            [
                nowcaster.predict(sample, valid_mask=sample_mask)
                for sample, sample_mask in zip(input_tensor, input_mask, strict=True)
            ],
            axis=0,
        )
    raise ValueError(
        "input tensor must be [time, height, width, channels] or "
        "[sample, time, height, width, channels]"
    )


def evaluate_optical_flow_tensor_archive(
    *,
    archive_path: Path,
    event_threshold: float = 35.0,
    max_displacement: int | None = 128,
    min_valid_pixels: int = 16,
    fill_value: float = 0.0,
) -> dict[str, object]:
    """Compare optical flow with Persistence on one tensor archive."""

    archive = load_tensor_archive(archive_path)
    input_tensor = np.asarray(archive["input"], dtype=np.float32)
    target_tensor = np.asarray(archive["target"], dtype=np.float32)
    metadata = archive["metadata"]
    spec = archive["spec"]
    nodata_values = nodata_values_from_metadata(metadata)
    input_mask = valid_value_mask(input_tensor, nodata_values)
    evaluation_mask = common_evaluation_mask(input_tensor, target_tensor, nodata_values)
    horizon = target_tensor.shape[0] if target_tensor.ndim == 4 else target_tensor.shape[1]
    persistence_prediction = persistence_predict(input_tensor, horizon=horizon)
    optical_flow_prediction = optical_flow_predict(
        input_tensor,
        horizon=horizon,
        input_mask=input_mask,
        max_displacement=max_displacement,
        min_valid_pixels=min_valid_pixels,
        fill_value=fill_value,
    )
    if optical_flow_prediction.shape != target_tensor.shape:
        raise ValueError(
            "optical-flow prediction and target shapes differ: "
            f"{optical_flow_prediction.shape} != {target_tensor.shape}"
        )

    persistence = evaluate_masked_arrays_with_mae(
        prediction=persistence_prediction,
        target=target_tensor,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
    )
    optical_flow = evaluate_masked_arrays_with_mae(
        prediction=optical_flow_prediction,
        target=target_tensor,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
    )
    cadence_minutes = int(spec.get("cadence_minutes", 0))
    persistence["lead_time_metrics"] = lead_time_breakdown_with_mae(
        prediction=persistence_prediction,
        target=target_tensor,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
        cadence_minutes=cadence_minutes,
    )
    optical_flow["lead_time_metrics"] = lead_time_breakdown_with_mae(
        prediction=optical_flow_prediction,
        target=target_tensor,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
        cadence_minutes=cadence_minutes,
    )
    return {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "archive": str(archive_path),
        "event_id": metadata.get("event_id", ""),
        "event_threshold": event_threshold,
        "event_threshold_units": str(spec.get("units", "")),
        "value_units": str(spec.get("units", "")),
        "archive_layout": metadata.get("archive_layout", "single_window"),
        "window_count": metadata.get("window_count", 1),
        "input_shape": list(input_tensor.shape),
        "target_shape": list(target_tensor.shape),
        "evaluation_mask": {
            "valid_pixel_count": int(evaluation_mask.sum()),
            "ignored_pixel_count": int(evaluation_mask.size - evaluation_mask.sum()),
        },
        "models": {
            "PersistenceNowcaster": persistence,
            "OpticalFlowNowcaster": optical_flow,
        },
        "comparison": {
            "rmse_delta_optical_flow_minus_persistence": round(
                float(optical_flow["rmse"]) - float(persistence["rmse"]),
                6,
            ),
            "mae_delta_optical_flow_minus_persistence": round(
                float(optical_flow["mae"]) - float(persistence["mae"]),
                6,
            ),
            "csi_delta_optical_flow_minus_persistence": round(
                float(optical_flow["event_metrics"]["csi"])
                - float(persistence["event_metrics"]["csi"]),
                6,
            ),
        },
        "optical_flow_metadata": {
            "motion_estimator": "fft_phase_correlation",
            "motion_model": "global_integer_translation",
            "deterministic": True,
            "max_displacement": max_displacement,
            "min_valid_pixels": min_valid_pixels,
            "fill_value": fill_value,
            "nodata_values": list(nodata_values),
        },
        "tensor_spec": spec,
        "metadata": metadata,
    }


def write_evaluation_result(result: dict[str, object], output_path: Path) -> None:
    schema = OpticalFlowComparisonSchema.model_validate(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(schema.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare deterministic optical flow with Persistence on a radar tensor archive."
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/processed/radar_tensor_sample.npz"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/optical_flow_evaluation.json"),
    )
    parser.add_argument("--event-threshold", type=float, default=35.0)
    parser.add_argument(
        "--max-displacement",
        type=int,
        default=128,
        help="Maximum absolute integer displacement searched per input step; use -1 for unlimited.",
    )
    parser.add_argument("--min-valid-pixels", type=int, default=16)
    parser.add_argument("--fill-value", type=float, default=0.0)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    max_displacement = None if args.max_displacement < 0 else args.max_displacement
    result = evaluate_optical_flow_tensor_archive(
        archive_path=args.archive,
        event_threshold=args.event_threshold,
        max_displacement=max_displacement,
        min_valid_pixels=args.min_valid_pixels,
        fill_value=args.fill_value,
    )
    write_evaluation_result(result, args.output)
    persistence = result["models"]["PersistenceNowcaster"]
    optical_flow = result["models"]["OpticalFlowNowcaster"]
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"archive": str(args.archive)},
        outputs={"evaluation": str(args.output)},
        row_counts={
            "input_frames": result["input_shape"][0],
            "target_frames": result["target_shape"][0]
            if len(result["target_shape"]) == 4
            else result["target_shape"][1],
        },
        metrics={
            "persistence_rmse": persistence["rmse"],
            "optical_flow_rmse": optical_flow["rmse"],
            "optical_flow_mae": optical_flow["mae"],
            "optical_flow_csi": optical_flow["event_metrics"]["csi"],
            "rmse_delta_optical_flow_minus_persistence": result["comparison"][
                "rmse_delta_optical_flow_minus_persistence"
            ],
        },
        metadata={
            "event_id": result["event_id"],
            "archive_layout": result["archive_layout"],
            "window_count": result["window_count"],
            "event_threshold": args.event_threshold,
            "event_threshold_units": result["event_threshold_units"],
            "valid_pixel_count": result["evaluation_mask"]["valid_pixel_count"],
            "ignored_pixel_count": result["evaluation_mask"]["ignored_pixel_count"],
            "motion_estimator": result["optical_flow_metadata"]["motion_estimator"],
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote optical-flow evaluation to {args.output}")


if __name__ == "__main__":
    main()
