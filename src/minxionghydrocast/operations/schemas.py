"""Pydantic response contracts for the operational HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from minxionghydrocast.ingestion.source_adapter import SourceProvenance

Mode = Literal["demo", "live"]
ProductType = Literal[
    "demo_fixture",
    "official_alert",
    "official_observation",
    "experimental_forecast",
    "derived_feature",
    "derived_reference",
]


class ResponseSchema(BaseModel):
    """Base contract shared by every JSON response."""

    model_config = ConfigDict(extra="forbid", strict=True)


class HealthResponse(ResponseSchema):
    status: Literal["ok"] = "ok"


class ErrorResponse(ResponseSchema):
    error: Literal["dataset unavailable", "not found"]
    path: str


class DatasetHealth(ResponseSchema):
    state: Literal[
        "healthy",
        "stale",
        "demo",
        "degraded",
        "invalid",
        "upstream_unhealthy",
        "coverage_missing",
    ]
    ready: bool
    observed_at: str
    age_minutes: float | None
    max_age_minutes: float = Field(ge=0)
    schema_sha256: str = Field(min_length=64, max_length=64)
    schema_errors: list[str]
    degradation_reasons: list[str] = Field(default_factory=list)
    persistent_state: Literal[
        "stale",
        "degraded",
        "upstream_unhealthy",
        "coverage_missing",
    ] | None = None


class AggregateHealth(ResponseSchema):
    state: Literal["healthy", "unhealthy", "unavailable", "demo", "collector_error"]
    ready: bool
    datasets: dict[str, str]


class DatasetStatus(ResponseSchema):
    product_type: ProductType
    path: str
    row_count: int = Field(ge=0)
    fields: list[str]
    schema_sha256: str = Field(min_length=64, max_length=64)
    sha256: str = Field(min_length=64, max_length=64)
    health: DatasetHealth
    source: SourceProvenance | None = None


class SnapshotSummary(ResponseSchema):
    snapshot_id: str
    mode: Mode
    completed_at: str
    health: AggregateHealth | None = None


class AttemptSummary(ResponseSchema):
    snapshot_id: str
    status: Literal["ok", "error"]
    completed_at: str
    failure_reason: str = ""


class StatusResponse(ResponseSchema):
    state: Literal[
        "healthy",
        "unhealthy",
        "unavailable",
        "demo",
        "collector_error",
        "storage_error",
        "uninitialized",
    ]
    ready: bool
    checked_at: str
    failure_reason: str | None = None
    latest_snapshot: SnapshotSummary | None
    latest_attempt: AttemptSummary | None
    datasets: dict[str, DatasetStatus]


class DatasetResponse(ResponseSchema):
    schema_version: Literal[1] = 1
    snapshot_id: str
    generated_at: str
    mode: Mode
    dataset: str
    product_type: ProductType
    notice: str
    health: DatasetHealth
    source: SourceProvenance | None = None
    row_count: int = Field(ge=0)
    records: list[dict[str, str]]

    @model_validator(mode="after")
    def row_count_matches_records(self) -> DatasetResponse:
        if self.row_count != len(self.records):
            raise ValueError("row_count must match the number of records")
        return self


class ForecastResponse(ResponseSchema):
    schema_version: Literal[1] = 1
    available: Literal[False] = False
    product_type: Literal["experimental_forecast"] = "experimental_forecast"
    notice: str
    reason: str
    records: list[dict[str, str]] = Field(default_factory=list, max_length=0)


class ShadowWindow(ResponseSchema):
    start_at: str
    end_at: str


class ShadowCriteriaResponse(ResponseSchema):
    lookback_hours: float = Field(gt=0)
    minimum_duration_hours: float = Field(ge=0)
    minimum_live_attempts: int = Field(ge=0)
    minimum_success_rate: float = Field(ge=0, le=1)
    minimum_readiness_rate: float = Field(ge=0, le=1)
    maximum_gap_minutes: float = Field(gt=0)
    required_heavy_rain_periods: int = Field(ge=0)


class ShadowMetrics(ResponseSchema):
    live_attempts: int = Field(ge=0)
    successful_attempts: int = Field(ge=0)
    ready_attempts: int = Field(ge=0)
    duration_hours: float = Field(ge=0)
    success_rate: float = Field(ge=0, le=1)
    readiness_rate: float = Field(ge=0, le=1)
    maximum_gap_minutes: float | None = Field(default=None, ge=0)
    confirmed_heavy_rain_periods: int = Field(ge=0)
    covered_heavy_rain_periods: int = Field(ge=0)


class ShadowChecks(ResponseSchema):
    duration: bool
    live_attempts: bool
    success_rate: bool
    readiness_rate: bool
    maximum_gap: bool
    heavy_rain_periods: bool
    storage_integrity: bool
    evidence_valid: bool


class ShadowResponse(ResponseSchema):
    state: Literal["storage_error", "not_evaluated", "passed", "blocked"]
    schema_version: Literal[1] | None = None
    evaluated_at: str | None = None
    window: ShadowWindow | None = None
    criteria: ShadowCriteriaResponse | None = None
    metrics: ShadowMetrics | None = None
    checks: ShadowChecks | None = None
    shadow_gate_passed: bool
    notification_allowed: bool
    notification_blockers: list[str]

    @model_validator(mode="after")
    def evaluated_report_is_complete(self) -> ShadowResponse:
        report_fields = (
            self.schema_version,
            self.evaluated_at,
            self.window,
            self.criteria,
            self.metrics,
            self.checks,
        )
        if self.state in {"passed", "blocked"} and any(
            value is None for value in report_fields
        ):
            raise ValueError("evaluated shadow responses require the complete report")
        if self.state == "passed" and not self.shadow_gate_passed:
            raise ValueError("passed state requires shadow_gate_passed=true")
        if self.state == "blocked" and self.shadow_gate_passed:
            raise ValueError("blocked state requires shadow_gate_passed=false")
        return self
