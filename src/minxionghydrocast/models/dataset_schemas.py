"""Pydantic contracts for reproducible radar datasets and catalogs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from minxionghydrocast.models.evaluation_schemas import LeadTimeMetricsSchema

REQUIRED_SPLITS = ("train", "validation", "test")


class DatasetSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DatasetMinimumCounts(DatasetSchema):
    train: int = Field(default=2, ge=1)
    validation: int = Field(default=1, ge=1)
    test: int = Field(default=2, ge=1)
    minxiong_test: int = Field(default=2, ge=1)


class RadarDatasetConfig(DatasetSchema):
    data_id: str = Field(min_length=1)
    source_format: Literal["cwa_opendata_grid"] = "cwa_opendata_grid"
    input_length: int = Field(default=6, ge=1)
    prediction_length: int = Field(default=6, ge=1)
    cadence_minutes: int = Field(default=10, ge=1)
    units: str = "dBZ"
    crs: str = "TWD67"
    window_stride_frames: int = Field(default=1, ge=1)
    event_threshold: float = 35.0
    minimum_counts: DatasetMinimumCounts = Field(default_factory=DatasetMinimumCounts)


class RadarDatasetEvent(DatasetSchema):
    event_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    name: str = Field(min_length=1)
    event_type: str = Field(min_length=1)
    region: str = Field(min_length=1)
    start_time: str = Field(min_length=1)
    end_time: str = Field(min_length=1)
    source: str = Field(min_length=1)
    evidence_candidate_id: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9][a-z0-9_.-]+$",
    )
    notes: str = ""

    @model_validator(mode="after")
    def validate_event(self) -> "RadarDatasetEvent":
        try:
            start = datetime.fromisoformat(self.start_time.replace("Z", "+00:00"))
            end = datetime.fromisoformat(self.end_time.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{self.event_id}: invalid event timestamp") from exc
        if start.tzinfo is None or end.tzinfo is None:
            raise ValueError(f"{self.event_id}: event timestamps must include a timezone")
        if end <= start:
            raise ValueError(f"{self.event_id}: end_time must be after start_time")
        if self.source.casefold() == "demo" or self.event_id.startswith("demo_"):
            raise ValueError(f"{self.event_id}: demo events are prohibited")
        if (
            self.event_id.startswith("cwa_o_a0059_candidate_")
            and self.evidence_candidate_id != self.event_id
        ):
            raise ValueError(
                f"{self.event_id}: discovered candidate requires evidence_candidate_id"
            )
        return self


class RadarDatasetManifest(DatasetSchema):
    schema_version: Literal["2.0"]
    split_strategy: Literal["event_based"]
    target: str = Field(min_length=1)
    dataset: RadarDatasetConfig
    events: list[RadarDatasetEvent] = Field(min_length=1)
    splits: dict[str, list[str]]
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_splits(self) -> "RadarDatasetManifest":
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event IDs must be unique")
        candidate_ids = [
            event.evidence_candidate_id
            for event in self.events
            if event.evidence_candidate_id is not None
        ]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("evidence candidate IDs must be unique")
        event_id_set = set(event_ids)
        assigned: dict[str, str] = {}
        minimums = self.dataset.minimum_counts
        expected_minimums = {
            "train": minimums.train,
            "validation": minimums.validation,
            "test": minimums.test,
        }
        if set(self.splits) != set(REQUIRED_SPLITS):
            raise ValueError("splits must contain exactly train, validation, and test")
        for split, minimum in expected_minimums.items():
            split_event_ids = self.splits[split]
            if len(split_event_ids) < minimum:
                raise ValueError(f"{split} split needs at least {minimum} real events")
            for event_id in split_event_ids:
                if event_id not in event_id_set:
                    raise ValueError(f"{split} references unknown event_id: {event_id}")
                if event_id in assigned:
                    raise ValueError(
                        f"event_id {event_id} appears in both {assigned[event_id]} and {split}"
                    )
                assigned[event_id] = split
        unassigned = event_id_set - set(assigned)
        if unassigned:
            raise ValueError(f"events are not assigned to a split: {', '.join(sorted(unassigned))}")
        by_id = {event.event_id: event for event in self.events}
        ordered_events = sorted(
            self.events,
            key=lambda event: datetime.fromisoformat(
                event.start_time.replace("Z", "+00:00")
            ),
        )
        for previous, current in zip(ordered_events, ordered_events[1:]):
            previous_end = datetime.fromisoformat(previous.end_time.replace("Z", "+00:00"))
            current_start = datetime.fromisoformat(current.start_time.replace("Z", "+00:00"))
            if current_start <= previous_end:
                raise ValueError(
                    f"event windows overlap: {previous.event_id} and {current.event_id}"
                )
        minxiong_test_count = sum(
            "minxiong" in by_id[event_id].region.casefold()
            for event_id in self.splits["test"]
        )
        if minxiong_test_count < minimums.minxiong_test:
            raise ValueError(
                f"test split needs at least {minimums.minxiong_test} Minxiong events"
            )
        return self

    def split_for(self, event_id: str) -> str:
        for split, event_ids in self.splits.items():
            if event_id in event_ids:
                return split
        raise KeyError(event_id)


class ArtifactRecord(DatasetSchema):
    kind: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)


class PersistenceMetrics(DatasetSchema):
    rmse: float
    csi: float
    pod: float
    far: float
    lead_time_metrics: list[LeadTimeMetricsSchema] = Field(min_length=1)


class EventCatalogEntry(DatasetSchema):
    event_id: str
    split: Literal["train", "validation", "test"]
    region: str
    source_data_id: str
    start_time: str
    end_time: str
    frame_count: int = Field(ge=1)
    window_count: int = Field(ge=1)
    artifacts: list[ArtifactRecord]
    persistence: PersistenceMetrics


class EventModelComparison(DatasetSchema):
    event_id: str
    split: Literal["validation", "test"]
    persistence_rmse: float
    persistence_csi: float
    tiny_unet_rmse: float
    tiny_unet_csi: float
    rmse_delta_tiny_unet_minus_persistence: float
    csi_delta_tiny_unet_minus_persistence: float
    persistence_lead_time_metrics: list[LeadTimeMetricsSchema] = Field(min_length=1)
    tiny_unet_lead_time_metrics: list[LeadTimeMetricsSchema] = Field(min_length=1)
    artifact: ArtifactRecord

    @model_validator(mode="after")
    def validate_lead_time_alignment(self) -> "EventModelComparison":
        persistence_leads = [
            metric.lead_time_minutes for metric in self.persistence_lead_time_metrics
        ]
        tiny_unet_leads = [
            metric.lead_time_minutes for metric in self.tiny_unet_lead_time_metrics
        ]
        if persistence_leads != tiny_unet_leads:
            raise ValueError("model comparison lead times must match")
        return self


class WeightedTinyUnetAssessment(DatasetSchema):
    checkpoint: ArtifactRecord
    training_result: ArtifactRecord
    training_event_ids: list[str]
    validation_event_ids: list[str]
    comparisons: list[EventModelComparison]
    promotion_gate_passed: bool
    promotion_gate_failures: list[str]

    @model_validator(mode="after")
    def validate_promotion_gate(self) -> "WeightedTinyUnetAssessment":
        if self.promotion_gate_passed == bool(self.promotion_gate_failures):
            raise ValueError("promotion gate status and failures are inconsistent")
        comparison_ids = [comparison.event_id for comparison in self.comparisons]
        if len(comparison_ids) != len(set(comparison_ids)):
            raise ValueError("model comparison event IDs must be unique")
        if set(self.training_event_ids) & set(self.validation_event_ids):
            raise ValueError("training and validation event IDs must be disjoint")
        return self


class DatasetCatalog(DatasetSchema):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: str
    dataset_id: str
    research_root: str
    source_data_id: str
    manifest: ArtifactRecord
    history_index: ArtifactRecord
    split_counts: dict[str, int]
    events: list[EventCatalogEntry]
    combined_archives: dict[str, ArtifactRecord]
    weighted_tiny_unet: WeightedTinyUnetAssessment | None = None
    forecast_publication_ready: bool = False
    forecast_publication_blockers: list[str]

    @model_validator(mode="after")
    def validate_catalog_consistency(self) -> "DatasetCatalog":
        if set(self.split_counts) != set(REQUIRED_SPLITS):
            raise ValueError("split_counts must contain exactly train, validation, and test")
        if set(self.combined_archives) != set(REQUIRED_SPLITS):
            raise ValueError("combined_archives must contain exactly train, validation, and test")
        actual_counts = {
            split: sum(event.split == split for event in self.events)
            for split in REQUIRED_SPLITS
        }
        if self.split_counts != actual_counts:
            raise ValueError("split_counts must match catalog events")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("catalog event IDs must be unique")
        if self.weighted_tiny_unet is None:
            if self.forecast_publication_ready:
                raise ValueError("forecast publication requires a model assessment")
        else:
            assessment = self.weighted_tiny_unet
            expected_ids = {
                split: {
                    event.event_id for event in self.events if event.split == split
                }
                for split in REQUIRED_SPLITS
            }
            comparison_ids = {
                split: {
                    comparison.event_id
                    for comparison in assessment.comparisons
                    if comparison.split == split
                }
                for split in ("validation", "test")
            }
            if set(assessment.training_event_ids) != expected_ids["train"]:
                raise ValueError("model assessment training events do not match catalog")
            if set(assessment.validation_event_ids) != expected_ids["validation"]:
                raise ValueError("model assessment validation events do not match catalog")
            if comparison_ids["validation"] != expected_ids["validation"]:
                raise ValueError("validation comparisons do not match catalog events")
            if comparison_ids["test"] != expected_ids["test"]:
                raise ValueError("test comparisons do not match catalog events")
            if self.forecast_publication_ready != assessment.promotion_gate_passed:
                raise ValueError("forecast publication must match the model promotion gate")
        if self.forecast_publication_ready == bool(self.forecast_publication_blockers):
            raise ValueError("forecast publication status and blockers are inconsistent")
        return self


class DatasetVerificationReport(DatasetSchema):
    schema_version: Literal["1.0"] = "1.0"
    verified_at: str
    status: Literal["ok", "error"]
    catalog: ArtifactRecord
    artifact_count: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    mismatches: list[str]

    @model_validator(mode="after")
    def validate_status(self) -> "DatasetVerificationReport":
        if (self.status == "ok") == bool(self.mismatches):
            raise ValueError("verification status and mismatches are inconsistent")
        return self
