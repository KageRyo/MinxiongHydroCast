"""Pydantic contracts for persisted nowcasting evaluation artifacts."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvaluationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class BinaryEventMetricsSchema(EvaluationSchema):
    hits: int = Field(ge=0)
    misses: int = Field(ge=0)
    false_alarms: int = Field(ge=0)
    correct_negatives: int = Field(ge=0)
    csi: float = Field(ge=0.0, le=1.0)
    pod: float = Field(ge=0.0, le=1.0)
    far: float = Field(ge=0.0, le=1.0)


class LeadTimeMetricsSchema(EvaluationSchema):
    lead_index: int = Field(ge=0)
    lead_time_minutes: int = Field(ge=1)
    rmse: float = Field(ge=0.0)
    event_metrics: BinaryEventMetricsSchema
    valid_pixel_count: int = Field(ge=1)
    ignored_pixel_count: int = Field(ge=0)


class ModelEvaluationSchema(EvaluationSchema):
    rmse: float = Field(ge=0.0)
    event_metrics: BinaryEventMetricsSchema
    valid_pixel_count: int = Field(ge=1)
    ignored_pixel_count: int = Field(ge=0)
    lead_time_metrics: list[LeadTimeMetricsSchema] = Field(min_length=1)


class PersistenceEvaluationSchema(EvaluationSchema):
    generated_at: str
    model: Literal["PersistenceNowcaster"]
    archive: str
    event_id: str
    archive_layout: str
    window_count: int = Field(ge=1)
    horizon: int = Field(ge=1)
    input_shape: list[int]
    target_shape: list[int]
    prediction_shape: list[int]
    rmse_mm: float = Field(ge=0.0)
    rmse: float = Field(ge=0.0)
    value_units: str
    rmse_units: str
    event_threshold_mm: float
    event_threshold: float
    event_threshold_units: str
    event_metrics: BinaryEventMetricsSchema
    lead_time_metrics: list[LeadTimeMetricsSchema] = Field(min_length=1)
    valid_pixel_count: int = Field(ge=1)
    ignored_pixel_count: int = Field(ge=0)
    nodata_values: list[float]
    tensor_spec: dict[str, Any]
    metadata: dict[str, Any]


class EvaluationMaskSchema(EvaluationSchema):
    valid_pixel_count: int = Field(ge=1)
    ignored_pixel_count: int = Field(ge=0)


class ModelComparisonSchema(EvaluationSchema):
    rmse_delta_tiny_unet_minus_persistence: float
    csi_delta_tiny_unet_minus_persistence: float


class TinyUnetMetadataSchema(EvaluationSchema):
    checkpoint: str
    device: str
    normalization: dict[str, Any]
    nodata_values: list[float]
    hidden_channels: int = Field(ge=1)
    batch_size: int = Field(ge=1)


class TorchBaselineComparisonSchema(EvaluationSchema):
    generated_at: str
    archive: str
    checkpoint: str
    event_id: str
    event_threshold: float
    event_threshold_units: str
    value_units: str
    archive_layout: str
    window_count: int = Field(ge=1)
    input_shape: list[int]
    target_shape: list[int]
    evaluation_mask: EvaluationMaskSchema
    models: dict[str, ModelEvaluationSchema]
    comparison: ModelComparisonSchema
    tiny_unet_metadata: TinyUnetMetadataSchema
    tensor_spec: dict[str, Any]
    metadata: dict[str, Any]

    @model_validator(mode="after")
    def validate_model_keys(self) -> "TorchBaselineComparisonSchema":
        expected = {"PersistenceNowcaster", "TinyUNetNowcaster"}
        if set(self.models) != expected:
            raise ValueError("models must contain PersistenceNowcaster and TinyUNetNowcaster")
        return self
