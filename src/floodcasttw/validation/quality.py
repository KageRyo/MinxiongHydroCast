"""Lightweight quality checks for CSV-style records."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationReport:
    row_count: int
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def require_fields(records: Iterable[dict[str, object]], required_fields: set[str]) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = sorted(field for field in required_fields if field not in record)
        if missing:
            errors.append(f"row {index}: missing {', '.join(missing)}")
    return errors


def require_non_empty_fields(
    records: Iterable[dict[str, object]],
    fields: set[str],
) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = sorted(field for field in fields if record.get(field) in ("", None))
        if missing:
            errors.append(f"row {index}: empty {', '.join(missing)}")
    return errors


def assert_no_demo_records(records: Iterable[dict[str, object]]) -> None:
    for index, record in enumerate(records, start=1):
        if record.get("資料模式") == "demo":
            raise ValueError(f"row {index}: demo record cannot be used as production data")


def validate_records(
    records: Iterable[dict[str, object]],
    *,
    required_fields: set[str],
    allow_demo: bool,
    required_non_empty: set[str] | None = None,
) -> ValidationReport:
    rows = list(records)
    errors = require_fields(rows, required_fields)
    if required_non_empty:
        errors.extend(require_non_empty_fields(rows, required_non_empty))
    if not allow_demo:
        for index, record in enumerate(rows, start=1):
            if record.get("資料模式") == "demo":
                errors.append(f"row {index}: demo record cannot be used as production data")
    return ValidationReport(row_count=len(rows), errors=errors)
