"""Pydantic contracts for persisted model-training artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TrainingSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class TrainingNormalizationSchema(TrainingSchema):
    method: Literal["z_score"]
    mean: float
    std: float = Field(gt=0.0)
    input_valid_pixel_count: int = Field(ge=1)
    target_valid_pixel_count: int = Field(ge=1)
    input_ignored_pixel_count: int = Field(ge=0)
    target_ignored_pixel_count: int = Field(ge=0)


class TrainingTensorSpecSchema(TrainingSchema):
    input_length: int = Field(ge=1)
    prediction_length: int = Field(ge=1)
    height: int = Field(ge=1)
    width: int = Field(ge=1)
    channels: int = Field(ge=1)
    cadence_minutes: int = Field(ge=1)
    units: str = Field(min_length=1)
    crs: str = Field(min_length=1)


class TinyUnetTrainingResultSchema(TrainingSchema):
    model: Literal["TinyUNetNowcaster"]
    archive: str = Field(min_length=1)
    validation_archive: str
    checkpoint: str = Field(min_length=1)
    epochs: int = Field(ge=1)
    device: Literal["cpu", "cuda"]
    seed: int
    resume_checkpoint: str
    multi_gpu: bool
    data_parallel: bool
    cuda_device_count: int = Field(ge=0)
    cuda_device_names: list[str]
    used_cuda_device_count: int = Field(ge=0)
    batch_repeats: int = Field(ge=1)
    batch_size: int = Field(ge=1)
    loss_function: Literal["mse", "weighted_mse", "threshold_focal_mse"]
    event_threshold: float
    event_weight: float = Field(ge=1.0)
    focal_gamma: float = Field(ge=0.0)
    validation_fraction: float = Field(ge=0.0, lt=1.0)
    early_stopping_patience: int = Field(ge=0)
    training_sample_count: int = Field(ge=1)
    validation_sample_count: int = Field(ge=0)
    validation_event_ids: list[str]
    input_shape: list[int] = Field(min_length=4, max_length=4)
    target_shape: list[int] = Field(min_length=4, max_length=4)
    normalization: TrainingNormalizationSchema
    nodata_values: list[float]
    loss_history: list[float] = Field(min_length=1)
    validation_loss_history: list[float]
    final_loss: float
    best_validation_loss: float | None
    best_epoch: int | None = Field(default=None, ge=1)
    early_stopped: bool
    tensor_spec: TrainingTensorSpecSchema
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def validate_training_result(self) -> "TinyUnetTrainingResultSchema":
        if len(self.loss_history) > self.epochs:
            raise ValueError("loss_history cannot contain more entries than configured epochs")
        if self.final_loss != self.loss_history[-1]:
            raise ValueError("final_loss must equal the final loss_history entry")
        if self.best_epoch is not None and self.best_epoch > len(self.loss_history):
            raise ValueError("best_epoch cannot exceed completed epochs")
        if self.validation_event_ids and not self.validation_archive:
            raise ValueError("validation_event_ids require validation_archive")
        if self.used_cuda_device_count > self.cuda_device_count:
            raise ValueError("used CUDA device count cannot exceed detected device count")
        return self
