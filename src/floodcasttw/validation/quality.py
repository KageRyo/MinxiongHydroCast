"""Lightweight quality checks for CSV-style records."""

from __future__ import annotations

from collections.abc import Iterable


def require_fields(records: Iterable[dict[str, object]], required_fields: set[str]) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records, start=1):
        missing = sorted(
            field
            for field in required_fields
            if field not in record or record[field] in ("", None)
        )
        if missing:
            errors.append(f"row {index}: missing {', '.join(missing)}")
    return errors


def assert_no_demo_records(records: Iterable[dict[str, object]]) -> None:
    for index, record in enumerate(records, start=1):
        if record.get("資料模式") == "demo":
            raise ValueError(f"row {index}: demo record cannot be used as production data")
