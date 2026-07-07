"""Inspect CWA Open Data grid JSON files."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_grid_inspection"

NODATA_PATTERNS = (
    re.compile(r"資料無效值為\s*([-+]?\d+(?:\.\d+)?)"),
    re.compile(r"無效值為\s*([-+]?\d+(?:\.\d+)?)"),
)
OUTSIDE_PATTERNS = (
    re.compile(r"觀測範圍外.*?以\s*([-+]?\d+(?:\.\d+)?)表示"),
    re.compile(r"品管流程移除.*?以\s*([-+]?\d+(?:\.\d+)?)表示"),
)
CRS_PATTERNS = (
    re.compile(r"使用之座標系統為([^，。；;]+)"),
    re.compile(r"為([^，。；;]+經緯網格)"),
)


@dataclass(frozen=True)
class CwaGridInspection:
    path: str
    data_id: str
    dataset_description: str
    sent: str
    data_time: str
    start_longitude: float
    start_latitude: float
    grid_resolution: float
    grid_dimension_x: int
    grid_dimension_y: int
    expected_value_count: int
    value_count: int
    units: str
    crs: str
    nodata_values: tuple[float, ...]
    min_value: float
    max_value: float
    negative_value_count: int
    valid: bool
    content_description: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "data_id": self.data_id,
            "dataset_description": self.dataset_description,
            "sent": self.sent,
            "data_time": self.data_time,
            "start_longitude": self.start_longitude,
            "start_latitude": self.start_latitude,
            "grid_resolution": self.grid_resolution,
            "grid_dimension_x": self.grid_dimension_x,
            "grid_dimension_y": self.grid_dimension_y,
            "expected_value_count": self.expected_value_count,
            "value_count": self.value_count,
            "units": self.units,
            "crs": self.crs,
            "nodata_values": list(self.nodata_values),
            "min_value": self.min_value,
            "max_value": self.max_value,
            "negative_value_count": self.negative_value_count,
            "valid": self.valid,
            "content_description": self.content_description,
        }


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _require_mapping(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must be an object")
    return payload


def _float_field(payload: dict[str, Any], name: str) -> float:
    if name not in payload:
        raise ValueError(f"missing parameterSet field: {name}")
    return float(payload[name])


def _int_field(payload: dict[str, Any], name: str) -> int:
    if name not in payload:
        raise ValueError(f"missing parameterSet field: {name}")
    return int(payload[name])


def _unit_from_parameters(params: dict[str, Any]) -> str:
    for name in ("Reflectivity", "Precipitation"):
        value = params.get(name)
        if value:
            return str(value)
    return ""


def _extract_values(content: str) -> list[float]:
    values = []
    for item in content.split(","):
        item = item.strip()
        if item:
            values.append(float(item))
    return values


def _extract_pattern_values(
    description: str,
    patterns: tuple[re.Pattern[str], ...],
) -> list[float]:
    values = []
    for pattern in patterns:
        for match in pattern.finditer(description):
            values.append(float(match.group(1)))
    return values


def _extract_crs(description: str) -> str:
    for pattern in CRS_PATTERNS:
        match = pattern.search(description)
        if match:
            return match.group(1).strip()
    return "needs_review"


def _build_grid_inspection(
    *,
    path: Path,
    data_id: str,
    dataset_description: str,
    sent: str,
    params: dict[str, Any],
    content_description: str,
    content: str,
) -> CwaGridInspection:
    values = _extract_values(content)

    grid_dimension_x = _int_field(params, "GridDimensionX")
    grid_dimension_y = _int_field(params, "GridDimensionY")
    expected_value_count = grid_dimension_x * grid_dimension_y
    nodata_values = sorted(
        {
            *_extract_pattern_values(content_description, NODATA_PATTERNS),
            *_extract_pattern_values(content_description, OUTSIDE_PATTERNS),
        }
    )
    if not nodata_values:
        nodata_values = sorted({value for value in values if value < 0})

    return CwaGridInspection(
        path=str(path),
        data_id=data_id,
        dataset_description=dataset_description,
        sent=sent,
        data_time=str(params.get("DateTime", "")),
        start_longitude=_float_field(params, "StartPointLongitude"),
        start_latitude=_float_field(params, "StartPointLatitude"),
        grid_resolution=_float_field(params, "GridResolution"),
        grid_dimension_x=grid_dimension_x,
        grid_dimension_y=grid_dimension_y,
        expected_value_count=expected_value_count,
        value_count=len(values),
        units=_unit_from_parameters(params),
        crs=_extract_crs(content_description),
        nodata_values=tuple(nodata_values),
        min_value=min(values),
        max_value=max(values),
        negative_value_count=sum(1 for value in values if value < 0),
        valid=len(values) == expected_value_count,
        content_description=content_description,
    )


def inspect_cwa_grid_json_file(path: Path) -> CwaGridInspection:
    root = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "root")
    cwa = _require_mapping(root.get("cwaopendata"), "cwaopendata")
    dataset = _require_mapping(cwa.get("dataset"), "dataset")
    dataset_info = _require_mapping(dataset.get("datasetInfo"), "datasetInfo")
    params = _require_mapping(dataset_info.get("parameterSet"), "parameterSet")
    contents = _require_mapping(dataset.get("contents"), "contents")
    return _build_grid_inspection(
        path=path,
        data_id=str(cwa.get("dataid", "")),
        dataset_description=str(dataset_info.get("datasetDescription", "")),
        sent=str(cwa.get("sent", "")),
        params=params,
        content_description=str(contents.get("contentDescription", "")),
        content=str(contents.get("content", "")),
    )


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _first_xml_text(root: ET.Element, name: str) -> str:
    for element in root.iter():
        if _local_name(element.tag) == name:
            return (element.text or "").strip()
    return ""


def inspect_cwa_grid_xml_file(path: Path) -> CwaGridInspection:
    root = ET.parse(path).getroot()
    params = {
        name: _first_xml_text(root, name)
        for name in (
            "StartPointLongitude",
            "StartPointLatitude",
            "GridResolution",
            "DateTime",
            "GridDimensionX",
            "GridDimensionY",
            "Reflectivity",
            "Precipitation",
        )
    }
    return _build_grid_inspection(
        path=path,
        data_id=_first_xml_text(root, "dataid"),
        dataset_description=_first_xml_text(root, "datasetDescription"),
        sent=_first_xml_text(root, "sent"),
        params=params,
        content_description=_first_xml_text(root, "contentDescription"),
        content=_first_xml_text(root, "content"),
    )


def inspect_cwa_grid_file(path: Path) -> CwaGridInspection:
    prefix = path.read_bytes()[:64].lstrip()
    if prefix.startswith(b"<"):
        return inspect_cwa_grid_xml_file(path)
    return inspect_cwa_grid_json_file(path)


def extract_cwa_grid_values(path: Path) -> tuple[CwaGridInspection, list[float]]:
    inspection = inspect_cwa_grid_file(path)
    prefix = path.read_bytes()[:64].lstrip()
    if prefix.startswith(b"<"):
        content = _first_xml_text(ET.parse(path).getroot(), "content")
    else:
        root = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "root")
        cwa = _require_mapping(root.get("cwaopendata"), "cwaopendata")
        dataset = _require_mapping(cwa.get("dataset"), "dataset")
        contents = _require_mapping(dataset.get("contents"), "contents")
        content = str(contents.get("content", ""))
    return inspection, _extract_values(content)


def write_inspection(path: Path, inspections: list[CwaGridInspection]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([inspection.to_dict() for inspection in inspections], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def check_cwa_grid_sequence(
    inspections: list[CwaGridInspection],
    *,
    expected_cadence_minutes: int = 10,
) -> dict[str, object]:
    errors: list[str] = []
    warnings: list[str] = []
    if not inspections:
        errors.append("sequence has no frames")
        return {
            "status": "error",
            "frame_count": 0,
            "expected_cadence_minutes": expected_cadence_minutes,
            "errors": errors,
            "warnings": warnings,
        }

    sorted_inspections = sorted(inspections, key=lambda item: parse_iso_datetime(item.data_time))
    first = sorted_inspections[0]
    reference = {
        "data_id": first.data_id,
        "start_longitude": first.start_longitude,
        "start_latitude": first.start_latitude,
        "grid_resolution": first.grid_resolution,
        "grid_dimension_x": first.grid_dimension_x,
        "grid_dimension_y": first.grid_dimension_y,
        "units": first.units,
        "crs": first.crs,
        "nodata_values": list(first.nodata_values),
    }

    for inspection in sorted_inspections:
        if not inspection.valid:
            errors.append(f"{inspection.path}: value_count does not match grid dimensions")
        checks = {
            "data_id": inspection.data_id,
            "start_longitude": inspection.start_longitude,
            "start_latitude": inspection.start_latitude,
            "grid_resolution": inspection.grid_resolution,
            "grid_dimension_x": inspection.grid_dimension_x,
            "grid_dimension_y": inspection.grid_dimension_y,
            "units": inspection.units,
            "crs": inspection.crs,
            "nodata_values": list(inspection.nodata_values),
        }
        for field, value in checks.items():
            if value != reference[field]:
                errors.append(f"{inspection.path}: {field} changed within sequence")

    deltas: list[float] = []
    for previous, current in zip(sorted_inspections, sorted_inspections[1:]):
        delta_minutes = (
            parse_iso_datetime(current.data_time) - parse_iso_datetime(previous.data_time)
        ).total_seconds() / 60
        deltas.append(delta_minutes)
        if delta_minutes != expected_cadence_minutes:
            errors.append(
                f"{previous.data_time} to {current.data_time}: expected "
                f"{expected_cadence_minutes} minutes, got {delta_minutes:g}"
            )

    if len(sorted_inspections) == 1:
        warnings.append("sequence has only one frame")

    return {
        "status": "ok" if not errors else "error",
        "frame_count": len(sorted_inspections),
        "data_id": first.data_id,
        "start_time": sorted_inspections[0].data_time,
        "end_time": sorted_inspections[-1].data_time,
        "expected_cadence_minutes": expected_cadence_minutes,
        "observed_cadence_minutes": deltas,
        "reference": reference,
        "frames": [inspection.to_dict() for inspection in sorted_inspections],
        "errors": errors,
        "warnings": warnings,
    }


def write_sequence_check(path: Path, result: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect CWA grid JSON schema.")
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/cwa_grid_inspection.json"),
    )
    parser.add_argument("--sequence-output", type=Path, default=None)
    parser.add_argument("--expected-cadence-minutes", type=int, default=10)
    parser.add_argument("--require-sequence-ok", action="store_true")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    inspections = [inspect_cwa_grid_file(path) for path in args.inputs]
    write_inspection(args.output, inspections)
    sequence_check = check_cwa_grid_sequence(
        inspections,
        expected_cadence_minutes=args.expected_cadence_minutes,
    )
    if args.sequence_output:
        write_sequence_check(args.sequence_output, sequence_check)

    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok"
        if all(inspection.valid for inspection in inspections)
        and sequence_check["status"] == "ok"
        else "needs_review",
        failure_reason="; ".join(sequence_check["errors"]),
        started_at=started_at,
        start_timer=start_timer,
        inputs={"files": [str(path) for path in args.inputs]},
        outputs={
            "inspection": str(args.output),
            "sequence_check": str(args.sequence_output) if args.sequence_output else "",
        },
        row_counts={
            "files": len(inspections),
            "values": sum(inspection.value_count for inspection in inspections),
        },
        metadata={
            "data_ids": [inspection.data_id for inspection in inspections],
            "sequence_status": sequence_check["status"],
            "expected_cadence_minutes": args.expected_cadence_minutes,
            "require_sequence_ok": args.require_sequence_ok,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote CWA grid inspection to {args.output}")
    if args.require_sequence_ok and sequence_check["status"] != "ok":
        raise SystemExit("[ERROR] CWA grid sequence failed validation.")


if __name__ == "__main__":
    main()
