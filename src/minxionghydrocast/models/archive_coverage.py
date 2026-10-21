"""Strict schedules and source references for read-only archive coverage."""

from datetime import timedelta
from typing import Literal

from pydantic import Field, field_validator, model_validator

from minxionghydrocast.models.rolling_backtest import Contract, aware_time


class CoverageFrame(Contract):
    data_time: str
    path: str = Field(min_length=1, max_length=4096)
    bytes: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')

    @field_validator('data_time')
    @classmethod
    def timestamp(cls, value: str) -> str:
        return aware_time(value).isoformat()


class SourceAttempt(Contract):
    data_time: str
    attempted_at: str
    data_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,80}$')
    http_status: int | None = Field(default=None, ge=100, le=599)
    failure_kind: Literal['http', 'authentication', 'rate_limit', 'transport', 'timeout', 'unknown'] = 'unknown'

    @field_validator('data_time', 'attempted_at')
    @classmethod
    def timestamp(cls, value: str) -> str:
        return aware_time(value).isoformat()


class CoverageEntry(Contract):
    event_id: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')
    data_id: Literal['O-A0059-001', 'O-B0045-001']
    start_time: str
    end_time: str
    cadence_minutes: int = Field(ge=1, le=1440)
    units: Literal['dBZ', 'mm']
    crs: Literal['TWD67', 'TWD67經緯網格', 'WGS84', 'EPSG:4326', 'EPSG:3821']
    frames: list[CoverageFrame] = Field(max_length=100000)
    attempts: list[SourceAttempt] = Field(default_factory=list, max_length=10000)

    @field_validator('start_time', 'end_time')
    @classmethod
    def timestamp(cls, value: str) -> str:
        return aware_time(value).isoformat()

    @model_validator(mode='after')
    def schedule(self):
        span = aware_time(self.end_time) - aware_time(self.start_time)
        step = timedelta(minutes=self.cadence_minutes)
        if span < timedelta() or span % step or span // step >= 100000:
            raise ValueError('invalid or excessive cadence schedule')
        expected_units = 'dBZ' if self.data_id == 'O-A0059-001' else 'mm'
        if self.units != expected_units:
            raise ValueError('product units do not match the source contract')
        return self

    def times(self) -> list[str]:
        start, end = aware_time(self.start_time), aware_time(self.end_time)
        step = timedelta(minutes=self.cadence_minutes)
        return [(start + step * i).isoformat() for i in range((end - start) // step + 1)]


class ArchiveInventory(Contract):
    schema_version: Literal['1.0']
    kind: Literal['archive_inventory']
    entries: list[CoverageEntry] = Field(max_length=1000)

    @model_validator(mode='after')
    def unique_entries(self):
        keys = [(e.event_id, e.data_id) for e in self.entries]
        if len(set(keys)) != len(keys) or sum(len(e.times()) for e in self.entries) > 100000:
            raise ValueError('duplicate entries or excessive total schedule')
        return self
