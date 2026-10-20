"""Strict input contracts for observation-derived, research-only rolling evaluation."""

from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def aware_time(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("observation/as-of timestamps must include a timezone")
    return result.astimezone(timezone.utc)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class RadarFrame(Contract):
    path: str = Field(min_length=1)
    data_time: str
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("data_time")
    @classmethod
    def timestamp(cls, value: str) -> str:
        return aware_time(value).isoformat()

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or path.as_posix() != value:
            raise ValueError("frame paths must be normalized, relative and inside the data root")
        return value


class BacktestEvent(Contract):
    event_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]+$")
    frames: list[RadarFrame] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_frames(self) -> "BacktestEvent":
        times = [f.data_time for f in self.frames]
        if len(set(times)) != len(times) or times != sorted(times):
            raise ValueError("event frames must have unique, increasing observation times")
        if len({f.path for f in self.frames}) != len(self.frames):
            raise ValueError("event frame paths must be unique")
        return self


class BacktestManifest(Contract):
    schema_version: Literal["1.0"]
    events: list[BacktestEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def independent_events(self) -> "BacktestManifest":
        if len({e.event_id for e in self.events}) != len(self.events):
            raise ValueError("event IDs must be unique")
        events = sorted(self.events, key=lambda e: e.frames[0].data_time)
        for left, right in zip(events, events[1:]):
            if left.frames[-1].data_time >= right.frames[0].data_time:
                raise ValueError("research event observation ranges must not overlap")
        return self


class BacktestConfig(Contract):
    input_length: int = Field(default=6, ge=1)
    horizon: int = Field(default=6, ge=1, le=6)
    cadence_minutes: int = Field(default=10, ge=1)
    event_threshold: float = 35.0
    models: list[Literal["persistence", "optical_flow"]] = Field(
        default_factory=lambda: ["persistence", "optical_flow"], min_length=1
    )
    max_displacement: int = Field(default=8, ge=0)
    min_valid_pixels: int = Field(default=16, ge=1)

    @model_validator(mode="after")
    def model_contract(self) -> "BacktestConfig":
        if len(set(self.models)) != len(self.models) or "persistence" not in self.models:
            raise ValueError("models must be unique and include the Persistence reference")
        if "optical_flow" in self.models and self.input_length < 2:
            raise ValueError("optical flow requires at least two input frames")
        return self
