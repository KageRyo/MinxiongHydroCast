"""Shared contracts for production data-source adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Protocol

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
    authority: str
    dataset_id: str
    source_url: str
    fetched_at: str
    schema_version: str
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


@dataclass(frozen=True)
class SourceResult:
    dataset: str
    records: list[dict[str, str]]
    provenance: SourceProvenance

    def __post_init__(self) -> None:
        if self.provenance.outcome == "empty" and self.records:
            raise ValueError("empty source outcome cannot contain records")
        if self.provenance.outcome != "empty" and not self.records:
            raise ValueError("non-empty source outcome requires records")


class SourceAdapter(Protocol):
    """Collect and normalize one external source into operational records."""

    @property
    def dataset(self) -> str: ...

    def collect(self) -> SourceResult: ...


class SourceAdapterError(RuntimeError):
    """Typed source failure safe to persist in run metadata."""

    def __init__(self, kind: SourceErrorKind, message: str) -> None:
        self.kind = kind
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
