"""Radar source adapters that feed the tensor conversion contract."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from floodcasttw.ingestion.cwa_grid import (
    CwaGridInspection,
    check_cwa_grid_sequence,
    extract_cwa_grid_values,
)
from floodcasttw.models.radar_tensor import RadarTensorSpec

CSV_PIXEL_GRID = "csv_pixel_grid"
CWA_OPEN_DATA_GRID = "cwa_opendata_grid"
SUPPORTED_SOURCE_FORMATS = (CSV_PIXEL_GRID, CWA_OPEN_DATA_GRID)
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
        load_all_frames: bool = False,
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
        load_all_frames: bool = False,
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


def _looks_like_collection_manifest(payload: object) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("frames"), list)
        and all(isinstance(frame, dict) and frame.get("output_path") for frame in payload["frames"])
    )


def resolve_cwa_grid_paths(input_path: Path) -> tuple[list[Path], str]:
    if input_path.is_dir():
        paths = sorted(
            path
            for path in input_path.iterdir()
            if path.is_file() and path.suffix.lower() in {".json", ".xml"}
        )
        if not paths:
            raise ValueError(f"CWA grid directory has no JSON/XML files: {input_path}")
        return paths, input_path.name

    if input_path.is_file():
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return [input_path], input_path.stem
        if _looks_like_collection_manifest(payload):
            base_dir = input_path.parent
            event_id = str(payload.get("event_id") or input_path.stem)
            paths = []
            for frame in payload["frames"]:
                candidate = Path(str(frame["output_path"]))
                if candidate.is_absolute() or candidate.exists():
                    paths.append(candidate)
                else:
                    paths.append(base_dir / candidate)
            return paths, event_id
        return [input_path], input_path.stem

    raise FileNotFoundError(f"CWA grid input not found: {input_path}")


@dataclass(frozen=True)
class CwaOpenDataGridAdapter:
    source_format: str = CWA_OPEN_DATA_GRID

    def load_sequence(
        self,
        *,
        input_path: Path,
        event_id: str | None,
        input_length: int,
        prediction_length: int,
        height: int | None = None,
        width: int | None = None,
        cadence_minutes: int = 10,
        units: str = "",
        crs: str = "",
        load_all_frames: bool = False,
    ) -> RadarSourceBatch:
        paths, inferred_event_id = resolve_cwa_grid_paths(input_path)
        selected_event_id = event_id or inferred_event_id
        total_length = input_length + prediction_length
        if len(paths) < total_length:
            raise ValueError(
                f"CWA grid sequence has {len(paths)} frames; needs at least {total_length}"
            )

        selected_paths = paths if load_all_frames else paths[:total_length]
        loaded = [extract_cwa_grid_values(path) for path in selected_paths]
        loaded.sort(key=lambda item: item[0].data_time)
        inspections = [inspection for inspection, _values in loaded]
        sequence_check = check_cwa_grid_sequence(
            inspections,
            expected_cadence_minutes=cadence_minutes,
        )
        if sequence_check["status"] != "ok":
            raise ValueError(
                "CWA grid sequence failed validation: " + "; ".join(sequence_check["errors"])
            )

        first = inspections[0]
        source_units = first.units if units in ("", VALUE_FIELD) else units
        source_crs = first.crs if crs in ("", "EPSG:4326") else crs
        spec = RadarTensorSpec(
            input_length=input_length,
            prediction_length=prediction_length,
            height=height or first.grid_dimension_y,
            width=width or first.grid_dimension_x,
            channels=1,
            cadence_minutes=cadence_minutes,
            units=source_units,
            crs=source_crs,
        )
        if spec.height != first.grid_dimension_y or spec.width != first.grid_dimension_x:
            raise ValueError(
                "requested tensor size does not match CWA grid dimensions: "
                f"requested {spec.height}x{spec.width}, source "
                f"{first.grid_dimension_y}x{first.grid_dimension_x}"
            )

        sequence = self._build_sequence(loaded, spec=spec)
        metadata = self._metadata(
            event_id=selected_event_id,
            input_path=input_path,
            inspections=inspections,
            sequence_check=sequence_check,
            source_record_count=sum(inspection.value_count for inspection in inspections),
        )
        return RadarSourceBatch(
            event_id=selected_event_id,
            source_format=self.source_format,
            sequence=sequence,
            spec=spec,
            metadata=metadata,
            source_record_count=int(metadata["source_record_count"]),
        )

    def _build_sequence(
        self,
        loaded: list[tuple[CwaGridInspection, list[float]]],
        *,
        spec: RadarTensorSpec,
    ) -> np.ndarray:
        sequence = np.empty(
            (len(loaded), spec.height, spec.width, spec.channels),
            dtype=np.float32,
        )
        for frame_index, (inspection, values) in enumerate(loaded):
            frame = np.asarray(values, dtype=np.float32).reshape(
                inspection.grid_dimension_y,
                inspection.grid_dimension_x,
            )
            sequence[frame_index, :, :, 0] = frame
        return sequence

    def _metadata(
        self,
        *,
        event_id: str,
        input_path: Path,
        inspections: list[CwaGridInspection],
        sequence_check: dict[str, object],
        source_record_count: int,
    ) -> dict[str, object]:
        first = inspections[0]
        return {
            "event_id": event_id,
            "source_format": self.source_format,
            "source_path": str(input_path),
            "source_paths": [inspection.path for inspection in inspections],
            "source_record_count": source_record_count,
            "frame_count": len(inspections),
            "data_times": [inspection.data_time for inspection in inspections],
            "cwa_data_id": first.data_id,
            "dataset_description": first.dataset_description,
            "start_longitude": first.start_longitude,
            "start_latitude": first.start_latitude,
            "grid_resolution": first.grid_resolution,
            "nodata_values": list(first.nodata_values),
            "sequence_check": sequence_check,
        }


def get_radar_source_adapter(source_format: str) -> RadarSourceAdapter:
    if source_format == CSV_PIXEL_GRID:
        return CsvPixelGridAdapter()
    if source_format == CWA_OPEN_DATA_GRID:
        return CwaOpenDataGridAdapter()
    raise ValueError(f"unsupported radar source format: {source_format}")
