"""Radar source adapters that feed the tensor conversion contract."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from floodcasttw.models.radar_tensor import RadarTensorSpec

CSV_PIXEL_GRID = "csv_pixel_grid"
VALUE_FIELD = "mm_per_hour"
CSV_PIXEL_FIELDS = {"event_id", "frame_index", "y", "x", VALUE_FIELD}


@dataclass(frozen=True)
class RadarSourceBatch:
    event_id: str
    source_format: str
    sequence: np.ndarray
    spec: RadarTensorSpec
    metadata: dict[str, object]
    source_record_count: int


class RadarSourceAdapter(Protocol):
    source_format: str

    def load_sequence(
        self,
        *,
        input_path: Path,
        event_id: str | None,
        input_length: int,
        prediction_length: int,
        height: int | None = None,
        width: int | None = None,
        cadence_minutes: int = 6,
        units: str = VALUE_FIELD,
        crs: str = "EPSG:4326",
    ) -> RadarSourceBatch:
        """Load a radar source into a model-ready sequence."""


def read_csv_pixel_records(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = CSV_PIXEL_FIELDS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing radar pixel fields: {', '.join(sorted(missing))}")
        return list(reader)


def select_event_id(records: list[dict[str, str]], event_id: str | None) -> str:
    event_ids = sorted({record["event_id"] for record in records})
    if not event_ids:
        raise ValueError("radar source has no records")
    if event_id:
        if event_id not in event_ids:
            raise ValueError(f"event_id not found in radar source: {event_id}")
        return event_id
    if len(event_ids) != 1:
        raise ValueError("radar source has multiple events; pass --event-id")
    return event_ids[0]


def infer_size(records: list[dict[str, str]], field: str) -> int:
    return max(int(record[field]) for record in records) + 1


@dataclass(frozen=True)
class CsvPixelGridAdapter:
    source_format: str = CSV_PIXEL_GRID

    def load_sequence(
        self,
        *,
        input_path: Path,
        event_id: str | None,
        input_length: int,
        prediction_length: int,
        height: int | None = None,
        width: int | None = None,
        cadence_minutes: int = 6,
        units: str = VALUE_FIELD,
        crs: str = "EPSG:4326",
    ) -> RadarSourceBatch:
        records = read_csv_pixel_records(input_path)
        return self.build_batch_from_records(
            records,
            event_id=event_id,
            input_length=input_length,
            prediction_length=prediction_length,
            height=height,
            width=width,
            cadence_minutes=cadence_minutes,
            units=units,
            crs=crs,
            source_path=input_path,
        )

    def build_batch_from_records(
        self,
        records: list[dict[str, str]],
        *,
        event_id: str | None,
        input_length: int,
        prediction_length: int,
        height: int | None = None,
        width: int | None = None,
        cadence_minutes: int = 6,
        units: str = VALUE_FIELD,
        crs: str = "EPSG:4326",
        source_path: Path | None = None,
    ) -> RadarSourceBatch:
        selected_event_id = select_event_id(records, event_id)
        selected = [record for record in records if record["event_id"] == selected_event_id]
        spec = RadarTensorSpec(
            input_length=input_length,
            prediction_length=prediction_length,
            height=height or infer_size(selected, "y"),
            width=width or infer_size(selected, "x"),
            channels=1,
            cadence_minutes=cadence_minutes,
            units=units,
            crs=crs,
        )
        sequence = self._build_sequence(selected, event_id=selected_event_id, spec=spec)
        metadata = {
            "event_id": selected_event_id,
            "source_format": self.source_format,
            "value_field": VALUE_FIELD,
            "frame_count": spec.total_length,
            "source_path": str(source_path) if source_path else "",
        }
        return RadarSourceBatch(
            event_id=selected_event_id,
            source_format=self.source_format,
            sequence=sequence,
            spec=spec,
            metadata=metadata,
            source_record_count=len(records),
        )

    def _build_sequence(
        self,
        records: list[dict[str, str]],
        *,
        event_id: str,
        spec: RadarTensorSpec,
    ) -> np.ndarray:
        sequence = np.full(
            (spec.total_length, spec.height, spec.width, spec.channels),
            np.nan,
            dtype=np.float32,
        )
        if spec.channels != 1:
            raise ValueError("CSV radar pixel conversion currently supports one channel")

        for record in records:
            frame_index = int(record["frame_index"])
            y = int(record["y"])
            x = int(record["x"])
            if not (0 <= frame_index < spec.total_length):
                raise ValueError(f"frame_index out of bounds for {event_id}: {frame_index}")
            if not (0 <= y < spec.height and 0 <= x < spec.width):
                raise ValueError(f"grid coordinate out of bounds for {event_id}: y={y}, x={x}")
            if not np.isnan(sequence[frame_index, y, x, 0]):
                raise ValueError(
                    f"duplicate pixel for {event_id}: frame={frame_index}, y={y}, x={x}"
                )
            sequence[frame_index, y, x, 0] = float(record[VALUE_FIELD])

        missing = np.argwhere(np.isnan(sequence))
        if missing.size:
            first = missing[0].tolist()
            raise ValueError(f"missing radar pixel for {event_id}: index={first}")
        return sequence


def get_radar_source_adapter(source_format: str) -> RadarSourceAdapter:
    if source_format == CSV_PIXEL_GRID:
        return CsvPixelGridAdapter()
    raise ValueError(f"unsupported radar source format: {source_format}")
