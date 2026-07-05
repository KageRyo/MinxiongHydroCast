"""CSV helpers with Taiwan-friendly UTF-8 BOM output."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path


def write_csv(
    records: Iterable[dict[str, object]],
    output_path: Path,
    fieldnames: Sequence[str],
) -> int:
    rows = list(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
