"""Evaluate a Tiny U-Net checkpoint against the persistence baseline."""

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
from minxionghydrocast.models.evaluation_schemas import TorchBaselineComparisonSchema
from minxionghydrocast.models.metrics import binary_event_metrics, rmse
from minxionghydrocast.models.radar_tensor import nodata_values_from_metadata, valid_value_mask
from minxionghydrocast.pipelines.radar_tensor_conversion import load_tensor_archive
from minxionghydrocast.pipelines.tensor_baseline_evaluation import (
    lead_time_breakdown,
    persistence_predict,
)
from minxionghydrocast.pipelines.torch_baseline_training import (
    array_to_channels_first,
    build_tiny_unet,
    prepare_channels_first_arrays,
    prepare_channels_first_masks,
    require_torch,
    select_device,
)

PIPELINE_NAME = "torch_baseline_evaluation"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def sequence_to_channels_first(array: np.ndarray) -> np.ndarray:
    return array_to_channels_first(array)


def channels_first_to_sequence(array: np.ndarray, target_tensor: np.ndarray) -> np.ndarray:
    values = np.asarray(array, dtype=np.float32)
    target = np.asarray(target_tensor)
    if target.ndim == 4:
        lead_count, height, width, channels = target.shape
        return values.reshape(1, lead_count, channels, height, width)[0].transpose(0, 2, 3, 1)
    if target.ndim == 5:
        sample_count, lead_count, height, width, channels = target.shape
        return values.reshape(
            sample_count,
            lead_count,
            channels,
            height,
            width,
        ).transpose(0, 1, 3, 4, 2)
    raise ValueError("target tensor must be 4D or 5D")


def normalize_with_metadata(
    model_input: np.ndarray,
    input_mask: np.ndarray,
    normalization: dict[str, object],
) -> np.ndarray:
    mean = float(normalization["mean"])
    std = float(normalization["std"])
    if std == 0.0:
        std = 1.0
    normalized = ((model_input - mean) / std).astype(np.float32)
    normalized[~input_mask] = 0.0
    return normalized


def denormalize_with_metadata(
    prediction: np.ndarray,
    normalization: dict[str, object],
) -> np.ndarray:
    mean = float(normalization["mean"])
    std = float(normalization["std"])
    return (np.asarray(prediction, dtype=np.float32) * std + mean).astype(np.float32)


def common_evaluation_mask_sequence(archive: dict[str, object]) -> np.ndarray:
    metadata = archive.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    nodata_values = nodata_values_from_metadata(metadata)
    input_tensor = np.asarray(archive["input"], dtype=np.float32)
    target_tensor = np.asarray(archive["target"], dtype=np.float32)
    target_mask = valid_value_mask(target_tensor, nodata_values)
    if input_tensor.ndim == 4:
        latest_input_mask = valid_value_mask(input_tensor[-1:], nodata_values)
        return target_mask & np.repeat(latest_input_mask, target_tensor.shape[0], axis=0)
    if input_tensor.ndim == 5:
        latest_input_mask = valid_value_mask(input_tensor[:, -1:, :, :, :], nodata_values)
        return target_mask & np.repeat(latest_input_mask, target_tensor.shape[1], axis=1)
    raise ValueError("unsupported input tensor rank")


def common_evaluation_mask(archive: dict[str, object]) -> np.ndarray:
    return sequence_to_channels_first(common_evaluation_mask_sequence(archive)).astype(bool)


def evaluate_prediction_arrays(
    *,
    prediction: np.ndarray,
    target: np.ndarray,
    evaluation_mask: np.ndarray,
    event_threshold: float,
) -> dict[str, object]:
    if prediction.shape != target.shape:
        raise ValueError(f"prediction and target shapes differ: {prediction.shape} != {target.shape}")
    if evaluation_mask.shape != target.shape:
        raise ValueError(f"mask and target shapes differ: {evaluation_mask.shape} != {target.shape}")
    valid_pixels = int(evaluation_mask.sum())
    if valid_pixels == 0:
        raise ValueError("evaluation mask has no valid pixels")
    prediction_valid = prediction[evaluation_mask]
    target_valid = target[evaluation_mask]
    event_metrics = binary_event_metrics(
        prediction_valid >= event_threshold,
        target_valid >= event_threshold,
    )
    return {
        "rmse": round(rmse(prediction_valid, target_valid), 6),
        "event_metrics": event_metrics.to_dict(),
        "valid_pixel_count": valid_pixels,
        "ignored_pixel_count": int(evaluation_mask.size - valid_pixels),
    }


def load_tiny_unet_prediction(
    *,
    archive: dict[str, object],
    checkpoint_path: Path,
    device: str,
    batch_size: int = 1,
) -> tuple[np.ndarray, dict[str, object], dict[str, object]]:
    torch, nn = require_torch()
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    checkpoint_config = checkpoint.get("config", {})
    normalization = checkpoint.get("normalization", {})
    if not isinstance(checkpoint_config, dict) or not isinstance(normalization, dict):
        raise ValueError("Tiny U-Net checkpoint is missing config or normalization metadata")

    model_input, model_target = prepare_channels_first_arrays(archive)
    input_mask, _target_mask, nodata_values = prepare_channels_first_masks(archive)
    normalized_input = normalize_with_metadata(model_input, input_mask, normalization)
    selected_device = select_device(torch, device)
    model = build_tiny_unet(
        nn,
        input_channels=model_input.shape[1],
        output_channels=model_target.shape[1],
        hidden_channels=int(checkpoint_config.get("hidden_channels", 16)),
    )
    model.load_state_dict(checkpoint["state_dict"])
    model.to(selected_device)
    model.eval()
    predictions = []
    with torch.no_grad():
        for start in range(0, normalized_input.shape[0], batch_size):
            stop = min(start + batch_size, normalized_input.shape[0])
            prediction = model(torch.from_numpy(normalized_input[start:stop]).to(selected_device))
            predictions.append(prediction.detach().cpu().numpy())
    denormalized = denormalize_with_metadata(
        np.concatenate(predictions, axis=0),
        normalization,
    )
    metadata = {
        "checkpoint": str(checkpoint_path),
        "device": selected_device,
        "normalization": normalization,
        "nodata_values": list(nodata_values),
        "hidden_channels": int(checkpoint_config.get("hidden_channels", 16)),
        "batch_size": batch_size,
    }
    return denormalized, metadata, checkpoint_config


def evaluate_torch_baseline_comparison(
    *,
    archive_path: Path,
    checkpoint_path: Path,
    event_threshold: float = 35.0,
    device: str = "auto",
    batch_size: int = 1,
) -> dict[str, object]:
    archive = load_tensor_archive(archive_path)
    input_tensor = np.asarray(archive["input"], dtype=np.float32)
    target_tensor = np.asarray(archive["target"], dtype=np.float32)
    _model_input, model_target = prepare_channels_first_arrays(archive)
    evaluation_mask_sequence = common_evaluation_mask_sequence(archive)
    evaluation_mask = sequence_to_channels_first(evaluation_mask_sequence).astype(bool)
    persistence_prediction = sequence_to_channels_first(
        persistence_predict(
            input_tensor,
            horizon=target_tensor.shape[0] if target_tensor.ndim == 4 else target_tensor.shape[1],
        )
    )
    tiny_unet_prediction, tiny_unet_metadata, _checkpoint_config = load_tiny_unet_prediction(
        archive=archive,
        checkpoint_path=checkpoint_path,
        device=device,
        batch_size=batch_size,
    )

    value_units = str(archive["spec"].get("units", ""))
    cadence_minutes = int(archive["spec"].get("cadence_minutes", 0))
    persistence_sequence = channels_first_to_sequence(persistence_prediction, target_tensor)
    tiny_unet_sequence = channels_first_to_sequence(tiny_unet_prediction, target_tensor)
    persistence = evaluate_prediction_arrays(
        prediction=persistence_prediction,
        target=model_target,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
    )
    tiny_unet = evaluate_prediction_arrays(
        prediction=tiny_unet_prediction,
        target=model_target,
        evaluation_mask=evaluation_mask,
        event_threshold=event_threshold,
    )
    persistence["lead_time_metrics"] = lead_time_breakdown(
        prediction=persistence_sequence,
        target=target_tensor,
        evaluation_mask=evaluation_mask_sequence,
        event_threshold=event_threshold,
        cadence_minutes=cadence_minutes,
    )
    tiny_unet["lead_time_metrics"] = lead_time_breakdown(
        prediction=tiny_unet_sequence,
        target=target_tensor,
        evaluation_mask=evaluation_mask_sequence,
        event_threshold=event_threshold,
        cadence_minutes=cadence_minutes,
    )
    return {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "archive": str(archive_path),
        "checkpoint": str(checkpoint_path),
        "event_id": archive["metadata"].get("event_id", ""),
        "event_threshold": event_threshold,
        "event_threshold_units": value_units,
        "value_units": value_units,
        "archive_layout": archive["metadata"].get("archive_layout", "single_window"),
        "window_count": archive["metadata"].get("window_count", 1),
        "input_shape": list(input_tensor.shape),
        "target_shape": list(target_tensor.shape),
        "evaluation_mask": {
            "valid_pixel_count": persistence["valid_pixel_count"],
            "ignored_pixel_count": persistence["ignored_pixel_count"],
        },
        "models": {
            "PersistenceNowcaster": persistence,
            "TinyUNetNowcaster": tiny_unet,
        },
        "comparison": {
            "rmse_delta_tiny_unet_minus_persistence": round(
                float(tiny_unet["rmse"]) - float(persistence["rmse"]),
                6,
            ),
            "csi_delta_tiny_unet_minus_persistence": round(
                float(tiny_unet["event_metrics"]["csi"])
                - float(persistence["event_metrics"]["csi"]),
                6,
            ),
        },
        "tiny_unet_metadata": tiny_unet_metadata,
        "tensor_spec": archive["spec"],
        "metadata": archive["metadata"],
    }


def write_evaluation_result(
    result: dict[str, object] | TorchBaselineComparisonSchema,
    output_path: Path,
) -> None:
    schema = TorchBaselineComparisonSchema.model_validate(result)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(schema.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate Tiny U-Net and persistence on the same tensor archive."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/torch_baseline_comparison.json"),
    )
    parser.add_argument("--event-threshold", type=float, default=35.0)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    result = evaluate_torch_baseline_comparison(
        archive_path=args.archive,
        checkpoint_path=args.checkpoint,
        event_threshold=args.event_threshold,
        device=args.device,
        batch_size=args.batch_size,
    )
    write_evaluation_result(result, args.output)
    tiny_unet = result["models"]["TinyUNetNowcaster"]
    persistence = result["models"]["PersistenceNowcaster"]
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"archive": str(args.archive), "checkpoint": str(args.checkpoint)},
        outputs={"evaluation": str(args.output)},
        metrics={
            "persistence_rmse": persistence["rmse"],
            "tiny_unet_rmse": tiny_unet["rmse"],
            "tiny_unet_csi": tiny_unet["event_metrics"]["csi"],
            "rmse_delta_tiny_unet_minus_persistence": result["comparison"][
                "rmse_delta_tiny_unet_minus_persistence"
            ],
        },
        metadata={
            "event_id": result["event_id"],
            "event_threshold": args.event_threshold,
            "event_threshold_units": result["event_threshold_units"],
            "device": result["tiny_unet_metadata"]["device"],
            "batch_size": result["tiny_unet_metadata"]["batch_size"],
            "valid_pixel_count": result["evaluation_mask"]["valid_pixel_count"],
            "ignored_pixel_count": result["evaluation_mask"]["ignored_pixel_count"],
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote Tiny U-Net comparison to {args.output}")


if __name__ == "__main__":
    main()
