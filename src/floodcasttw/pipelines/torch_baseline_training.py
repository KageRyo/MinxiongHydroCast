"""Optional PyTorch training for a small radar nowcasting baseline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.radar_tensor import nodata_values_from_metadata, valid_value_mask
from floodcasttw.pipelines.radar_tensor_conversion import load_tensor_archive

PIPELINE_NAME = "torch_baseline_training"


@dataclass(frozen=True)
class TorchTrainingConfig:
    archive_path: Path
    output_dir: Path
    epochs: int = 3
    learning_rate: float = 1e-3
    hidden_channels: int = 16
    device: str = "auto"
    seed: int = 42
    resume_checkpoint: Path | None = None
    multi_gpu: bool = False
    batch_repeats: int = 1
    batch_size: int = 1
    loss_function: str = "mse"
    event_threshold: float = 35.0
    event_weight: float = 1.0
    focal_gamma: float = 0.0
    validation_fraction: float = 0.0
    early_stopping_patience: int = 0


def prepare_channels_first_arrays(archive: dict[str, object]) -> tuple[np.ndarray, np.ndarray]:
    input_tensor = np.asarray(archive["input"], dtype=np.float32)
    target_tensor = np.asarray(archive["target"], dtype=np.float32)
    return arrays_to_channels_first(input_tensor, target_tensor)


def array_to_channels_first(array: np.ndarray) -> np.ndarray:
    values = np.asarray(array)
    if values.ndim == 4:
        return values.transpose(0, 3, 1, 2).reshape(
            1,
            values.shape[0] * values.shape[3],
            values.shape[1],
            values.shape[2],
        )
    if values.ndim == 5:
        return values.transpose(0, 1, 4, 2, 3).reshape(
            values.shape[0],
            values.shape[1] * values.shape[4],
            values.shape[2],
            values.shape[3],
        )
    raise ValueError(
        "arrays must be [time, height, width, channels] or "
        "[sample, time, height, width, channels]"
    )


def arrays_to_channels_first(
    input_array: np.ndarray,
    target_array: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    model_input = array_to_channels_first(input_array)
    model_target = array_to_channels_first(target_array)
    if model_input.shape[0] != model_target.shape[0]:
        raise ValueError("input and target tensors must have the same sample count")
    return model_input, model_target


def prepare_channels_first_masks(
    archive: dict[str, object],
) -> tuple[np.ndarray, np.ndarray, tuple[float, ...]]:
    metadata = archive.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    nodata_values = nodata_values_from_metadata(metadata)
    input_mask = valid_value_mask(archive["input"], nodata_values)
    target_mask = valid_value_mask(archive["target"], nodata_values)
    input_channels, target_channels = arrays_to_channels_first(input_mask, target_mask)
    return input_channels.astype(bool), target_channels.astype(bool), nodata_values


def repeat_training_batch(
    model_input: np.ndarray,
    model_target: np.ndarray,
    *,
    batch_repeats: int,
) -> tuple[np.ndarray, np.ndarray]:
    if batch_repeats < 1:
        raise ValueError("batch_repeats must be at least 1")
    if batch_repeats == 1:
        return model_input, model_target
    return (
        np.repeat(model_input, batch_repeats, axis=0),
        np.repeat(model_target, batch_repeats, axis=0),
    )


def normalize_training_arrays(
    model_input: np.ndarray,
    model_target: np.ndarray,
    input_mask: np.ndarray,
    target_mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, dict[str, object]]:
    valid_values = np.concatenate(
        [
            model_input[input_mask].astype(np.float64),
            model_target[target_mask].astype(np.float64),
        ]
    )
    if valid_values.size == 0:
        raise ValueError("training archive has no valid pixels after nodata masking")
    mean = float(valid_values.mean())
    std = float(valid_values.std())
    if std == 0.0:
        std = 1.0

    normalized_input = ((model_input - mean) / std).astype(np.float32)
    normalized_target = ((model_target - mean) / std).astype(np.float32)
    normalized_input[~input_mask] = 0.0
    normalized_target[~target_mask] = 0.0
    return normalized_input, normalized_target, {
        "method": "z_score",
        "mean": round(mean, 6),
        "std": round(std, 6),
        "input_valid_pixel_count": int(input_mask.sum()),
        "target_valid_pixel_count": int(target_mask.sum()),
        "input_ignored_pixel_count": int(input_mask.size - int(input_mask.sum())),
        "target_ignored_pixel_count": int(target_mask.size - int(target_mask.sum())),
    }


def build_loss_weights(
    model_target: np.ndarray,
    target_mask: np.ndarray,
    *,
    loss_function: str = "mse",
    event_threshold: float = 35.0,
    event_weight: float = 1.0,
    focal_gamma: float = 0.0,
) -> np.ndarray:
    if event_weight < 1.0:
        raise ValueError("event_weight must be at least 1.0")
    if focal_gamma < 0.0:
        raise ValueError("focal_gamma must be non-negative")
    if loss_function not in {"mse", "weighted_mse", "threshold_focal_mse"}:
        raise ValueError("loss_function must be one of: mse, weighted_mse, threshold_focal_mse")
    weights = np.ones_like(model_target, dtype=np.float32)
    if loss_function in {"weighted_mse", "threshold_focal_mse"}:
        weights = np.where(model_target >= event_threshold, event_weight, weights).astype(np.float32)
    if loss_function == "threshold_focal_mse":
        scale = max(abs(event_threshold), 1.0)
        exceedance = np.maximum(model_target - event_threshold, 0.0) / scale
        weights = (weights * (1.0 + focal_gamma * np.square(exceedance))).astype(np.float32)
    weights[~target_mask] = 0.0
    return weights


def masked_mse_loss(prediction, target, target_mask, loss_weights=None):
    if not bool(target_mask.any()):
        raise ValueError("training target mask has no valid pixels")
    squared_error = (prediction - target) ** 2
    if loss_weights is None:
        return squared_error[target_mask].mean()
    weights = loss_weights[target_mask]
    weight_sum = weights.sum()
    if not bool(weight_sum > 0):
        raise ValueError("training target weights have no positive valid pixels")
    return (squared_error[target_mask] * weights).sum() / weight_sum


def training_validation_indices(
    sample_count: int,
    *,
    validation_fraction: float,
    seed: int,
) -> tuple[list[int], list[int]]:
    if sample_count < 1:
        raise ValueError("sample_count must be at least 1")
    if validation_fraction < 0.0 or validation_fraction >= 1.0:
        raise ValueError("validation_fraction must be in [0.0, 1.0)")
    indices = np.arange(sample_count)
    if validation_fraction == 0.0:
        return indices.tolist(), []
    if sample_count < 2:
        raise ValueError("validation_fraction requires at least two samples")
    rng = np.random.default_rng(seed)
    rng.shuffle(indices)
    validation_count = int(round(sample_count * validation_fraction))
    validation_count = min(max(validation_count, 1), sample_count - 1)
    validation = sorted(indices[:validation_count].tolist())
    training = sorted(indices[validation_count:].tolist())
    return training, validation


def require_torch() -> tuple[Any, Any]:
    try:
        import torch
        from torch import nn
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyTorch is required for training. Install the model extra and a CUDA-compatible "
            "torch build before running this command."
        ) from exc
    return torch, nn


def select_device(torch: Any, requested: str) -> str:
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
    return requested


def cuda_device_names(torch: Any) -> list[str]:
    if not torch.cuda.is_available():
        return []
    return [torch.cuda.get_device_name(index) for index in range(torch.cuda.device_count())]


def build_tiny_unet(nn: Any, *, input_channels: int, output_channels: int, hidden_channels: int):
    class TinyUNetNowcaster(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.encoder = nn.Sequential(
                nn.Conv2d(input_channels, hidden_channels, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Conv2d(hidden_channels, hidden_channels, kernel_size=3, padding=1),
                nn.ReLU(),
            )
            self.pool = nn.MaxPool2d(2)
            self.middle = nn.Sequential(
                nn.Conv2d(hidden_channels, hidden_channels * 2, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Conv2d(hidden_channels * 2, hidden_channels, kernel_size=3, padding=1),
                nn.ReLU(),
            )
            self.decoder = nn.Sequential(
                nn.Conv2d(hidden_channels, hidden_channels, kernel_size=3, padding=1),
                nn.ReLU(),
                nn.Conv2d(hidden_channels, output_channels, kernel_size=1),
            )

        def forward(self, tensor):
            encoded = self.encoder(tensor)
            middle = self.middle(self.pool(encoded))
            upsampled = nn.functional.interpolate(
                middle,
                size=encoded.shape[-2:],
                mode="bilinear",
                align_corners=False,
            )
            return self.decoder(upsampled + encoded)

    return TinyUNetNowcaster()


def train_tiny_unet_archive(config: TorchTrainingConfig) -> dict[str, object]:
    torch, nn = require_torch()
    if config.batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    archive = load_tensor_archive(config.archive_path)
    model_input, model_target = prepare_channels_first_arrays(archive)
    input_mask, target_mask, nodata_values = prepare_channels_first_masks(archive)
    model_input, model_target = repeat_training_batch(
        model_input,
        model_target,
        batch_repeats=config.batch_repeats,
    )
    input_mask, target_mask = repeat_training_batch(
        input_mask,
        target_mask,
        batch_repeats=config.batch_repeats,
    )
    loss_weights = build_loss_weights(
        model_target,
        target_mask,
        loss_function=config.loss_function,
        event_threshold=config.event_threshold,
        event_weight=config.event_weight,
        focal_gamma=config.focal_gamma,
    )
    model_input, model_target, normalization = normalize_training_arrays(
        model_input,
        model_target,
        input_mask,
        target_mask,
    )
    device = select_device(torch, config.device)
    torch.manual_seed(config.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(config.seed)
    torch.backends.cudnn.benchmark = False

    x = torch.from_numpy(model_input).to(device)
    y = torch.from_numpy(model_target).to(device)
    y_mask = torch.from_numpy(target_mask).to(device)
    y_weights = torch.from_numpy(loss_weights).to(device)
    model = build_tiny_unet(
        nn,
        input_channels=model_input.shape[1],
        output_channels=model_target.shape[1],
        hidden_channels=config.hidden_channels,
    ).to(device)
    if config.resume_checkpoint:
        checkpoint = torch.load(config.resume_checkpoint, map_location=device)
        model.load_state_dict(checkpoint["state_dict"])
    cuda_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
    use_data_parallel = config.multi_gpu and device == "cuda" and cuda_count > 1
    if config.multi_gpu and device != "cuda":
        raise RuntimeError("--multi-gpu requires CUDA")
    if config.multi_gpu and cuda_count < 2:
        raise RuntimeError("--multi-gpu requires at least two visible CUDA devices")
    if use_data_parallel:
        model = nn.DataParallel(model)
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate)
    training_indices, validation_indices = training_validation_indices(
        int(x.shape[0]),
        validation_fraction=config.validation_fraction,
        seed=config.seed,
    )

    def current_model_state() -> dict[str, Any]:
        state = model.module.state_dict() if use_data_parallel else model.state_dict()
        return {key: value.detach().cpu().clone() for key, value in state.items()}

    def load_model_state(state: dict[str, Any]) -> None:
        if use_data_parallel:
            model.module.load_state_dict(state)
        else:
            model.load_state_dict(state)

    def evaluate_indices(indices: list[int]) -> float:
        if not indices:
            raise ValueError("cannot evaluate an empty index set")
        losses_for_indices = []
        with torch.no_grad():
            for start in range(0, len(indices), config.batch_size):
                batch_indices = indices[start : start + config.batch_size]
                prediction = model(x[batch_indices])
                loss = masked_mse_loss(
                    prediction,
                    y[batch_indices],
                    y_mask[batch_indices],
                    y_weights[batch_indices],
                )
                losses_for_indices.append(float(loss.detach().cpu().item()))
        return round(float(np.mean(losses_for_indices)), 6)

    losses: list[float] = []
    validation_losses: list[float] = []
    best_validation_loss: float | None = None
    best_epoch: int | None = None
    best_state: dict[str, Any] | None = None
    epochs_without_improvement = 0
    early_stopped = False
    model.train()
    for epoch in range(config.epochs):
        batch_losses = []
        for start in range(0, len(training_indices), config.batch_size):
            batch_indices = training_indices[start : start + config.batch_size]
            optimizer.zero_grad(set_to_none=True)
            prediction = model(x[batch_indices])
            loss = masked_mse_loss(
                prediction,
                y[batch_indices],
                y_mask[batch_indices],
                y_weights[batch_indices],
            )
            loss.backward()
            optimizer.step()
            batch_losses.append(float(loss.detach().cpu().item()))
        losses.append(round(float(np.mean(batch_losses)), 6))
        if validation_indices:
            model.eval()
            validation_loss = evaluate_indices(validation_indices)
            validation_losses.append(validation_loss)
            model.train()
            if best_validation_loss is None or validation_loss < best_validation_loss:
                best_validation_loss = validation_loss
                best_epoch = epoch + 1
                best_state = current_model_state()
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if (
                    config.early_stopping_patience > 0
                    and epochs_without_improvement >= config.early_stopping_patience
                ):
                    early_stopped = True
                    break

    if best_state is not None:
        load_model_state(best_state)

    config.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = config.output_dir / "tiny_unet_nowcaster.pt"
    result_path = config.output_dir / "tiny_unet_training_result.json"
    model_state = model.module.state_dict() if use_data_parallel else model.state_dict()
    checkpoint = {
        "model_name": "TinyUNetNowcaster",
        "state_dict": model_state,
        "config": {
            "epochs": config.epochs,
            "learning_rate": config.learning_rate,
            "hidden_channels": config.hidden_channels,
            "device": device,
            "seed": config.seed,
            "resume_checkpoint": str(config.resume_checkpoint or ""),
            "multi_gpu": config.multi_gpu,
            "batch_repeats": config.batch_repeats,
            "batch_size": config.batch_size,
            "loss_function": config.loss_function,
            "event_threshold": config.event_threshold,
            "event_weight": config.event_weight,
            "focal_gamma": config.focal_gamma,
            "validation_fraction": config.validation_fraction,
            "early_stopping_patience": config.early_stopping_patience,
        },
        "normalization": normalization,
        "nodata_values": list(nodata_values),
        "loss_history": losses,
        "validation_loss_history": validation_losses,
        "tensor_spec": archive["spec"],
        "metadata": archive["metadata"],
    }
    torch.save(checkpoint, checkpoint_path)
    result = {
        "model": "TinyUNetNowcaster",
        "archive": str(config.archive_path),
        "checkpoint": str(checkpoint_path),
        "epochs": config.epochs,
        "device": device,
        "seed": config.seed,
        "resume_checkpoint": str(config.resume_checkpoint or ""),
        "multi_gpu": config.multi_gpu,
        "data_parallel": use_data_parallel,
        "cuda_device_count": cuda_count,
        "cuda_device_names": cuda_device_names(torch),
        "used_cuda_device_count": cuda_count if use_data_parallel else int(device == "cuda"),
        "batch_repeats": config.batch_repeats,
        "batch_size": config.batch_size,
        "loss_function": config.loss_function,
        "event_threshold": config.event_threshold,
        "event_weight": config.event_weight,
        "focal_gamma": config.focal_gamma,
        "validation_fraction": config.validation_fraction,
        "early_stopping_patience": config.early_stopping_patience,
        "training_sample_count": len(training_indices),
        "validation_sample_count": len(validation_indices),
        "input_shape": list(model_input.shape),
        "target_shape": list(model_target.shape),
        "normalization": normalization,
        "nodata_values": list(nodata_values),
        "loss_history": losses,
        "validation_loss_history": validation_losses,
        "final_loss": losses[-1] if losses else None,
        "best_validation_loss": best_validation_loss,
        "best_epoch": best_epoch,
        "early_stopped": early_stopped,
        "tensor_spec": archive["spec"],
        "metadata": archive["metadata"],
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a small PyTorch nowcasting baseline.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/external/checkpoints/tiny_unet"))
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--hidden-channels", type=int, default=16)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume-checkpoint", type=Path, default=None)
    parser.add_argument("--multi-gpu", action="store_true")
    parser.add_argument("--batch-repeats", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument(
        "--loss-function",
        choices=["mse", "weighted_mse", "threshold_focal_mse"],
        default="mse",
    )
    parser.add_argument("--event-threshold", type=float, default=35.0)
    parser.add_argument("--event-weight", type=float, default=1.0)
    parser.add_argument("--focal-gamma", type=float, default=0.0)
    parser.add_argument("--validation-fraction", type=float, default=0.0)
    parser.add_argument("--early-stopping-patience", type=int, default=0)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    config = TorchTrainingConfig(
        archive_path=args.archive,
        output_dir=args.output_dir,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        hidden_channels=args.hidden_channels,
        device=args.device,
        seed=args.seed,
        resume_checkpoint=args.resume_checkpoint,
        multi_gpu=args.multi_gpu,
        batch_repeats=args.batch_repeats,
        batch_size=args.batch_size,
        loss_function=args.loss_function,
        event_threshold=args.event_threshold,
        event_weight=args.event_weight,
        focal_gamma=args.focal_gamma,
        validation_fraction=args.validation_fraction,
        early_stopping_patience=args.early_stopping_patience,
    )
    try:
        result = train_tiny_unet_archive(config)
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="ok",
            started_at=started_at,
            start_timer=start_timer,
            inputs={"archive": str(args.archive)},
            outputs={"checkpoint": result["checkpoint"]},
            row_counts={"epochs": args.epochs},
            metrics={"final_loss": result["final_loss"]},
            metadata={
                "model": result["model"],
                "device": result["device"],
                "hidden_channels": args.hidden_channels,
                "seed": args.seed,
                "resume_checkpoint": str(args.resume_checkpoint or ""),
                "multi_gpu": args.multi_gpu,
                "batch_repeats": args.batch_repeats,
                "batch_size": args.batch_size,
                "loss_function": args.loss_function,
                "event_threshold": args.event_threshold,
                "event_weight": args.event_weight,
                "focal_gamma": args.focal_gamma,
                "validation_fraction": args.validation_fraction,
                "early_stopping_patience": args.early_stopping_patience,
                "used_cuda_device_count": result["used_cuda_device_count"],
                "cuda_device_names": result["cuda_device_names"],
                "normalization": result["normalization"],
                "nodata_values": result["nodata_values"],
                "training_sample_count": result["training_sample_count"],
                "validation_sample_count": result["validation_sample_count"],
                "best_validation_loss": result["best_validation_loss"],
                "best_epoch": result["best_epoch"],
                "early_stopped": result["early_stopped"],
            },
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        print(f"[OK] Trained TinyUNetNowcaster -> {result['checkpoint']}")
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=str(exc),
            started_at=started_at,
            start_timer=start_timer,
            inputs={"archive": str(args.archive)},
            outputs={"checkpoint": ""},
            metadata={
                "device": args.device,
                "hidden_channels": args.hidden_channels,
                "seed": args.seed,
                "resume_checkpoint": str(args.resume_checkpoint or ""),
                "multi_gpu": args.multi_gpu,
                "batch_repeats": args.batch_repeats,
                "batch_size": args.batch_size,
                "loss_function": args.loss_function,
                "event_threshold": args.event_threshold,
                "event_weight": args.event_weight,
                "focal_gamma": args.focal_gamma,
                "validation_fraction": args.validation_fraction,
                "early_stopping_patience": args.early_stopping_patience,
            },
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
