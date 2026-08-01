"""Shared contracts for production data-source adapters."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceKind = Literal["api", "scraper_fallback", "demo_fixture"]
SourceOutcome = Literal["ok", "empty", "stale", "fallback"]
SourceErrorKind = Literal[
    "authentication",
    "empty_unexpected",
    "http",
    "rate_limited",
    "schema_drift",
    "stale",
    "transport",
]


class SourceProvenance(BaseModel):
    """Auditable metadata attached to one collected dataset."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_kind: SourceKind
    outcome: SourceOutcome
    authority: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    fetched_at: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    fallback_reason_kind: SourceErrorKind | None = None
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def source_kind_matches_outcome(self) -> SourceProvenance:
        if self.source_kind == "scraper_fallback" and self.outcome != "fallback":
            raise ValueError("scraper_fallback source requires fallback outcome")
        if self.source_kind != "scraper_fallback" and self.outcome == "fallback":
            raise ValueError("fallback outcome requires scraper_fallback source")
        if self.source_kind == "demo_fixture" and self.outcome != "ok":
            raise ValueError("demo_fixture source requires ok outcome")
        if self.fallback_reason_kind is not None and self.source_kind != "scraper_fallback":
            raise ValueError("fallback reason kind requires scraper_fallback source")
        return self


class SourceRetryCount(BaseModel):
    """One bounded retry counter safe to expose in summaries and metrics."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    reason: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    count: int = Field(ge=1)


class SourceRetryMetrics(BaseModel):
    """Retry counts for one source adapter collection attempt."""

    model_config = ConfigDict(extra="forbid", strict=True)

    total: int = Field(default=0, ge=0)
    counts: list[SourceRetryCount] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_counts(self) -> SourceRetryMetrics:
        keys = [(item.source, item.reason) for item in self.counts]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("retry counters must be unique and sorted")
        if self.total != sum(item.count for item in self.counts):
            raise ValueError("retry total must match retry counters")
        return self

    @classmethod
    def from_counter(
        cls,
        counter: Counter[tuple[str, str]] | dict[tuple[str, str], int],
    ) -> SourceRetryMetrics:
        counts = [
            SourceRetryCount(source=source, reason=reason, count=count)
            for (source, reason), count in sorted(counter.items())
            if count > 0
        ]
        return cls(total=sum(item.count for item in counts), counts=counts)


@dataclass(frozen=True)
class SourceResult:
    dataset: str
    records: list[dict[str, str]]
    provenance: SourceProvenance
    retry_metrics: SourceRetryMetrics = field(default_factory=SourceRetryMetrics)

    def __post_init__(self) -> None:
        if self.provenance.outcome == "empty" and self.records:
            raise ValueError("empty source outcome cannot contain records")
        if self.provenance.outcome != "empty" and not self.records:
            raise ValueError("non-empty source outcome requires records")


@runtime_checkable
class SourceAdapter(Protocol):
    """Public adapter contract for one atomic fetch-and-validate transaction."""

    source_id: str
    adapter_version: str

    @property
    def dataset(self) -> str: ...

    def collect(self) -> SourceResult: ...


class SourceAdapterError(RuntimeError):
    """Typed source failure safe to persist in run metadata."""

    def __init__(
        self,
        kind: SourceErrorKind,
        message: str,
        *,
        dataset: str | None = None,
        retry_metrics: SourceRetryMetrics | None = None,
    ) -> None:
        self.kind = kind
        self.dataset = dataset
        self.retry_metrics = retry_metrics or SourceRetryMetrics()
        super().__init__(message)


class SourceRequestError(SourceAdapterError):
    """Request failure that may use a degraded fallback."""


class SourceSchemaError(SourceAdapterError):
    """Contract failure that must reject the collection attempt."""


def records_sha256(records: list[dict[str, str]]) -> str:
    payload = json.dumps(
        records,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_adapter_contract(
    adapter: SourceAdapter,
    result: SourceResult,
) -> SourceResult:
    """Validate adapter identity, provenance, timestamp, and checksum invariants.

    Adapter authors can use this after ``collect()`` in contract tests. It intentionally performs
    no network request itself, so a test can supply a deterministic fixture transport.
    """

    if not isinstance(adapter.source_id, str) or not adapter.source_id.strip():
        raise ValueError("adapter source_id must be a non-empty string")
    if not isinstance(adapter.adapter_version, str) or not adapter.adapter_version.strip():
        raise ValueError("adapter adapter_version must be a non-empty string")
    if not isinstance(adapter.dataset, str) or not adapter.dataset.strip():
        raise ValueError("adapter dataset must be a non-empty string")
    if result.dataset != adapter.dataset:
        raise ValueError(
            f"adapter dataset mismatch: expected {adapter.dataset}, got {result.dataset}"
        )
    if result.provenance.dataset_id != adapter.source_id:
        raise ValueError(
            "adapter source_id must match provenance dataset_id: "
            f"{adapter.source_id} != {result.provenance.dataset_id}"
        )
    if result.provenance.schema_version != adapter.adapter_version:
        raise ValueError(
            "adapter_version must match provenance schema_version: "
            f"{adapter.adapter_version} != {result.provenance.schema_version}"
        )
    try:
        fetched_at = datetime.fromisoformat(result.provenance.fetched_at)
    except ValueError as exc:
        raise ValueError("adapter fetched_at must be an ISO-8601 timestamp") from exc
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise ValueError("adapter fetched_at must include a UTC offset")
    try:
        checksum = bytes.fromhex(result.provenance.content_sha256)
    except ValueError as exc:
        raise ValueError("adapter content_sha256 must be hexadecimal") from exc
    if len(checksum) != 32:
        raise ValueError("adapter content_sha256 must contain 32 bytes")
    return result
