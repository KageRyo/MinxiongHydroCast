"""Strict contracts for continuously discovered radar-event evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from minxionghydrocast.ingestion.source_adapter import SourceProvenance
from minxionghydrocast.models.dataset_schemas import ArtifactRecord

RadarDataId = Literal["O-A0059-001"]
QpeDataId = Literal["O-B0045-001"]
GaugeDataId = Literal["O-A0002-001"]
WarningDataId = Literal["WRA-Rainfall-Warning-v2"]
WeatherRegime = Literal["unclassified", "typhoon", "front", "mei_yu", "convective", "other"]


def aware_datetime(value: str, *, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed


class EventEvidenceSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class DiscoveryConfig(EventEvidenceSchema):
    radar_data_id: RadarDataId = "O-A0059-001"
    qpe_data_id: QpeDataId = "O-B0045-001"
    gauge_data_id: GaugeDataId = "O-A0002-001"
    warning_data_id: WarningDataId = "WRA-Rainfall-Warning-v2"
    cadence_minutes: int = Field(default=10, ge=1)
    event_threshold_dbz: float = Field(default=35.0, gt=0)
    local_longitude: float = Field(default=120.43, ge=-180, le=180)
    local_latitude: float = Field(default=23.55, ge=-90, le=90)
    local_radius_pixels: int = Field(default=8, ge=0)
    local_min_pixels: int = Field(default=1, ge=1)
    taiwan_min_pixels: int = Field(default=1000, ge=1)
    initial_lookback_minutes: int = Field(default=120, ge=10)
    merge_gap_minutes: int = Field(default=60, ge=10)
    before_minutes: int = Field(default=60, ge=10)
    after_minutes: int = Field(default=60, ge=10)
    evidence_max_alignment_minutes: int = Field(default=20, ge=0)

    @model_validator(mode="after")
    def validate_cadence_alignment(self) -> "DiscoveryConfig":
        for field in (
            "initial_lookback_minutes",
            "merge_gap_minutes",
            "before_minutes",
            "after_minutes",
        ):
            if getattr(self, field) % self.cadence_minutes:
                raise ValueError(f"{field} must align to cadence_minutes")
        return self


class DiscoveryCursor(EventEvidenceSchema):
    last_scanned_data_time: str | None = None
    last_successful_scan_at: str | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> "DiscoveryCursor":
        if self.last_scanned_data_time is not None:
            aware_datetime(self.last_scanned_data_time, field="last_scanned_data_time")
        if self.last_successful_scan_at is not None:
            aware_datetime(self.last_successful_scan_at, field="last_successful_scan_at")
        return self


class CoverageMetric(EventEvidenceSchema):
    valid_pixel_count: int = Field(ge=0)
    pixels_ge_threshold: int = Field(ge=0)
    fraction_ge_threshold: float = Field(ge=0, le=1)
    max_value: float | None = None

    @model_validator(mode="after")
    def validate_counts(self) -> "CoverageMetric":
        if self.pixels_ge_threshold > self.valid_pixel_count:
            raise ValueError("threshold pixel count exceeds valid pixel count")
        return self


class RadarFrameMetric(EventEvidenceSchema):
    data_time: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_bytes: int = Field(ge=1)
    threshold_dbz: float = Field(gt=0)
    local: CoverageMetric
    taiwan: CoverageMetric
    candidate_labels: tuple[
        Literal["minxiong_35dbz", "taiwan_wide_35dbz"], ...
    ] = ()

    @model_validator(mode="after")
    def validate_metric(self) -> "RadarFrameMetric":
        aware_datetime(self.data_time, field="data_time")
        if len(self.candidate_labels) != len(set(self.candidate_labels)):
            raise ValueError("candidate labels must be unique")
        return self


class CandidateRadarCollection(EventEvidenceSchema):
    expected_frame_count: int = Field(ge=1)
    captured_frame_count: int = Field(ge=0)
    missing_data_times: tuple[str, ...]
    plan: ArtifactRecord | None = None
    collection: ArtifactRecord | None = None
    frames: tuple[ArtifactRecord, ...] = ()
    complete: bool = False

    @model_validator(mode="after")
    def validate_collection(self) -> "CandidateRadarCollection":
        if self.captured_frame_count != len(self.frames):
            raise ValueError("captured_frame_count does not match frame artifacts")
        if self.captured_frame_count + len(self.missing_data_times) != self.expected_frame_count:
            raise ValueError("captured and missing frames do not match expected_frame_count")
        if len({artifact.path for artifact in self.frames}) != len(self.frames):
            raise ValueError("candidate frame artifact paths must be unique")
        for value in self.missing_data_times:
            aware_datetime(value, field="missing_data_times")
        if self.complete != (not self.missing_data_times):
            raise ValueError("complete must match missing_data_times")
        if self.complete and (self.plan is None or self.collection is None):
            raise ValueError("complete collection requires plan and collection artifacts")
        return self


class EvidenceSourceRecord(EventEvidenceSchema):
    dataset_id: str = Field(min_length=1)
    status: Literal["ok", "empty", "stale", "error"]
    observed_at: str | None = None
    alignment_delta_minutes: float | None = Field(default=None, ge=0)
    artifact: ArtifactRecord | None = None
    provenance: SourceProvenance | None = None
    failure_kind: str | None = None
    failure_reason: str | None = None

    @model_validator(mode="after")
    def validate_source_result(self) -> "EvidenceSourceRecord":
        if self.observed_at is not None:
            aware_datetime(self.observed_at, field="observed_at")
        if self.status == "error":
            if self.artifact is not None or not self.failure_kind or not self.failure_reason:
                raise ValueError("error evidence requires failure metadata and no artifact")
        else:
            if self.artifact is None or self.failure_kind is not None or self.failure_reason is not None:
                raise ValueError("successful evidence requires an artifact and no failure metadata")
        return self


class NormalizedSourceSnapshot(EventEvidenceSchema):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    target_data_time: str
    dataset: str = Field(min_length=1)
    records: list[dict[str, str]]
    provenance: SourceProvenance

    @model_validator(mode="after")
    def validate_snapshot(self) -> "NormalizedSourceSnapshot":
        aware_datetime(self.target_data_time, field="target_data_time")
        if self.dataset not in {"rain_gauges", "rainfall_alerts"}:
            raise ValueError("unsupported synchronized evidence dataset")
        if self.provenance.outcome == "empty" and self.records:
            raise ValueError("empty source snapshot cannot contain records")
        if self.provenance.outcome != "empty" and not self.records:
            raise ValueError("non-empty source snapshot requires records")
        return self


class SynchronizedEvidenceCapture(EventEvidenceSchema):
    capture_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    target_data_time: str
    captured_at: str
    qpe: EvidenceSourceRecord
    gauges: EvidenceSourceRecord
    warnings: EvidenceSourceRecord

    @model_validator(mode="after")
    def validate_capture(self) -> "SynchronizedEvidenceCapture":
        aware_datetime(self.target_data_time, field="target_data_time")
        aware_datetime(self.captured_at, field="captured_at")
        expected_ids = (
            self.qpe.dataset_id,
            self.gauges.dataset_id,
            self.warnings.dataset_id,
        )
        if expected_ids != ("O-B0045-001", "O-A0002-001", "WRA-Rainfall-Warning-v2"):
            raise ValueError("synchronized evidence dataset IDs are invalid")
        return self


class EventCandidate(EventEvidenceSchema):
    candidate_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    source_data_id: RadarDataId = "O-A0059-001"
    queue: Literal["candidate_only"] = "candidate_only"
    operational_status: Literal["collecting", "awaiting_review", "incomplete"]
    review_status: Literal["pending", "approved", "rejected"] = "pending"
    formal_split_membership: Literal["not_added"] = "not_added"
    weather_regime: WeatherRegime = "unclassified"
    first_trigger_time: str
    last_trigger_time: str
    window_start_time: str
    window_end_time: str
    candidate_labels: tuple[
        Literal["minxiong_35dbz", "taiwan_wide_35dbz"], ...
    ]
    triggers: tuple[RadarFrameMetric, ...]
    radar_collection: CandidateRadarCollection
    evidence_captures: tuple[SynchronizedEvidenceCapture, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(self) -> "EventCandidate":
        first = aware_datetime(self.first_trigger_time, field="first_trigger_time")
        last = aware_datetime(self.last_trigger_time, field="last_trigger_time")
        start = aware_datetime(self.window_start_time, field="window_start_time")
        end = aware_datetime(self.window_end_time, field="window_end_time")
        if not start < first <= last < end:
            raise ValueError("candidate trigger and window ordering is invalid")
        trigger_times = [metric.data_time for metric in self.triggers]
        if not trigger_times or len(trigger_times) != len(set(trigger_times)):
            raise ValueError("candidate trigger data times must be non-empty and unique")
        if trigger_times != sorted(trigger_times, key=lambda value: aware_datetime(value, field="trigger")):
            raise ValueError("candidate triggers must be chronological")
        if self.first_trigger_time != trigger_times[0] or self.last_trigger_time != trigger_times[-1]:
            raise ValueError("candidate trigger boundaries do not match triggers")
        expected_labels = tuple(sorted({label for metric in self.triggers for label in metric.candidate_labels}))
        if tuple(sorted(self.candidate_labels)) != expected_labels:
            raise ValueError("candidate labels do not match trigger metrics")
        capture_ids = [capture.capture_id for capture in self.evidence_captures]
        if len(capture_ids) != len(set(capture_ids)):
            raise ValueError("evidence capture IDs must be unique")
        if self.radar_collection.complete and self.operational_status != "awaiting_review":
            raise ValueError("complete candidate must await human review")
        if not self.radar_collection.complete and self.operational_status == "awaiting_review":
            raise ValueError("incomplete candidate cannot await review")
        if self.review_status == "approved" and not self.radar_collection.complete:
            raise ValueError("human review cannot approve an incomplete candidate")
        return self


class EventEvidenceCatalog(EventEvidenceSchema):
    schema_version: Literal["1.0"] = "1.0"
    updated_at: str
    research_root: str
    config: DiscoveryConfig
    cursor: DiscoveryCursor
    candidate_queue_only: Literal[True] = True
    automatic_formal_split_updates: Literal[False] = False
    retraining_policy: Literal["only_after_human_approved_new_events"] = (
        "only_after_human_approved_new_events"
    )
    history_indexes: tuple[ArtifactRecord, ...] = ()
    candidates: tuple[EventCandidate, ...] = ()

    @model_validator(mode="after")
    def validate_catalog(self) -> "EventEvidenceCatalog":
        aware_datetime(self.updated_at, field="updated_at")
        candidate_ids = [candidate.candidate_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate IDs must be unique")
        trigger_times = [
            trigger.data_time
            for candidate in self.candidates
            for trigger in candidate.triggers
        ]
        if len(trigger_times) != len(set(trigger_times)):
            raise ValueError("a radar frame cannot trigger more than one candidate")
        history_paths = [artifact.path for artifact in self.history_indexes]
        if len(history_paths) != len(set(history_paths)):
            raise ValueError("history index artifacts must be unique")
        return self
