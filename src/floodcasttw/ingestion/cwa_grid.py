"""Inspect CWA Open Data grid JSON files."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def inspect_cwa_grid_file(path: Path) -> CwaGridInspection:
    root = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "root")
    cwa = _require_mapping(root.get("cwaopendata"), "cwaopendata")
    dataset = _require_mapping(cwa.get("dataset"), "dataset")
    dataset_info = _require_mapping(dataset.get("datasetInfo"), "datasetInfo")
    params = _require_mapping(dataset_info.get("parameterSet"), "parameterSet")
    contents = _require_mapping(dataset.get("contents"), "contents")
    content_description = str(contents.get("contentDescription", ""))
    content = str(contents.get("content", ""))
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
        data_id=str(cwa.get("dataid", "")),
        dataset_description=str(dataset_info.get("datasetDescription", "")),
        sent=str(cwa.get("sent", "")),
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


def write_inspection(path: Path, inspections: list[CwaGridInspection]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([inspection.to_dict() for inspection in inspections], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect CWA grid JSON schema.")
    parser.add_argument("inputs", type=Path, nargs="+")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/cwa_grid_inspection.json"),
    )
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
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok" if all(inspection.valid for inspection in inspections) else "needs_review",
        failure_reason="",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"files": [str(path) for path in args.inputs]},
        outputs={"inspection": str(args.output)},
        row_counts={
            "files": len(inspections),
            "values": sum(inspection.value_count for inspection in inspections),
        },
        metadata={"data_ids": [inspection.data_id for inspection in inspections]},
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote CWA grid inspection to {args.output}")


if __name__ == "__main__":
    main()
