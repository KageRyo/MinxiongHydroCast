"""Validate CWA QPE grids against rain-gauge observations."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from floodcasttw.ingestion.cwa_grid import CwaGridInspection, extract_cwa_grid_values
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.metrics import rmse

PIPELINE_NAME = "qpe_gauge_validation"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")

STATION_ID_KEYS = ("StationId", "StationID", "stationId", "station_id", "id")
STATION_NAME_KEYS = ("StationName", "stationName", "Name", "name")
LATITUDE_KEYS = ("StationLatitude", "Latitude", "latitude", "lat")
LONGITUDE_KEYS = ("StationLongitude", "Longitude", "longitude", "lon", "lng")
DEFAULT_RAINFALL_KEYS = (
    "Past1hr",
    "Past1Hr",
    "Past1Hour",
    "past1hr",
    "past1Hour",
    "hourlyRainfall",
    "rainfall",
)
INVALID_RAINFALL_VALUES = {-99.0, -999.0, -1.0}
DEFAULT_XML_RAINFALL_WINDOWS = ("Past1hr", "Past1Hr", "Past1Hour")


@dataclass(frozen=True)
class GaugeObservation:
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    rainfall_mm: float
    data_time: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "rainfall_mm": self.rainfall_mm,
            "data_time": self.data_time,
        }


@dataclass(frozen=True)
class QpeGaugeMatch:
    station_id: str
    station_name: str
    latitude: float
    longitude: float
    gauge_mm: float
    qpe_mm: float | None
    difference_mm: float | None
    absolute_error_mm: float | None
    grid_row: int | None
    grid_col: int | None
    status: str
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "station_id": self.station_id,
            "station_name": self.station_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "gauge_mm": self.gauge_mm,
            "qpe_mm": self.qpe_mm,
            "difference_mm": self.difference_mm,
            "absolute_error_mm": self.absolute_error_mm,
            "grid_row": self.grid_row,
            "grid_col": self.grid_col,
            "status": self.status,
            "reason": self.reason,
        }


def _iter_dicts(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        found.append(payload)
        for value in payload.values():
            found.extend(_iter_dicts(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_iter_dicts(item))
    return found


def _first_string(payload: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _parse_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(parsed):
        return None
    return parsed


def _first_nested_float(payload: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for item in _iter_dicts(payload):
        for key in keys:
            parsed = _parse_float(item.get(key))
            if parsed is not None:
                return parsed
    return None


def _first_data_time(payload: dict[str, Any]) -> str:
    for item in _iter_dicts(payload):
        for key in ("DateTime", "dataTime", "DataTime", "time", "Time"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
    return ""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    for child in list(element):
        if _local_name(child.tag) == name:
            return child
    return None


def _child_text(element: ET.Element, path: tuple[str, ...]) -> str:
    node: ET.Element | None = element
    for name in path:
        node = _child(node, name) if node is not None else None
    if node is None or node.text is None:
        return ""
    return node.text.strip()


def _station_xml_coordinates(station: ET.Element) -> tuple[float | None, float | None]:
    geo_info = _child(station, "GeoInfo")
    if geo_info is None:
        return None, None
    coordinates = [
        child for child in list(geo_info) if _local_name(child.tag) == "Coordinates"
    ]
    selected = None
    for coordinate in coordinates:
        if _child_text(coordinate, ("CoordinateName",)).upper() == "WGS84":
            selected = coordinate
            break
    if selected is None and coordinates:
        selected = coordinates[0]
    if selected is None:
        return None, None
    return (
        _parse_float(_child_text(selected, ("StationLatitude",))),
        _parse_float(_child_text(selected, ("StationLongitude",))),
    )


def _station_xml_rainfall(
    station: ET.Element,
    *,
    rainfall_windows: tuple[str, ...],
) -> float | None:
    rainfall_element = _child(station, "RainfallElement")
    if rainfall_element is None:
        return None
    for window_name in rainfall_windows:
        window = _child(rainfall_element, window_name)
        if window is None:
            continue
        parsed = _parse_float(_child_text(window, ("Precipitation",)))
        if parsed is None:
            parsed = _parse_float(window.text.strip() if window.text else "")
        if parsed is not None:
            return parsed
    return None


def extract_gauge_observations_from_xml(
    xml_text: str,
    *,
    rainfall_windows: tuple[str, ...] = DEFAULT_XML_RAINFALL_WINDOWS,
) -> list[GaugeObservation]:
    root = ET.fromstring(xml_text)
    observations = []
    seen: set[tuple[str, str]] = set()
    for station in root.iter():
        if _local_name(station.tag) != "Station":
            continue
        station_id = _child_text(station, ("StationId",))
        station_name = _child_text(station, ("StationName",))
        data_time = _child_text(station, ("ObsTime", "DateTime"))
        latitude, longitude = _station_xml_coordinates(station)
        rainfall = _station_xml_rainfall(station, rainfall_windows=rainfall_windows)
        if latitude is None or longitude is None or rainfall is None:
            continue
        if rainfall in INVALID_RAINFALL_VALUES or rainfall < 0:
            continue
        key = (station_id or station_name, data_time)
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            GaugeObservation(
                station_id=station_id,
                station_name=station_name,
                latitude=latitude,
                longitude=longitude,
                rainfall_mm=rainfall,
                data_time=data_time,
            )
        )
    return observations


def extract_gauge_observations(
    payload: dict[str, Any],
    *,
    rainfall_keys: tuple[str, ...] = DEFAULT_RAINFALL_KEYS,
) -> list[GaugeObservation]:
    observations: list[GaugeObservation] = []
    seen: set[tuple[str, str]] = set()
    for item in _iter_dicts(payload):
        station_id = _first_string(item, STATION_ID_KEYS)
        station_name = _first_string(item, STATION_NAME_KEYS)
        if not station_id and not station_name:
            continue
        latitude = _first_nested_float(item, LATITUDE_KEYS)
        longitude = _first_nested_float(item, LONGITUDE_KEYS)
        rainfall = _first_nested_float(item, rainfall_keys)
        if latitude is None or longitude is None or rainfall is None:
            continue
        if rainfall in INVALID_RAINFALL_VALUES or rainfall < 0:
            continue
        key = (station_id or station_name, _first_data_time(item))
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            GaugeObservation(
                station_id=station_id,
                station_name=station_name,
                latitude=latitude,
                longitude=longitude,
                rainfall_mm=rainfall,
                data_time=_first_data_time(item),
            )
        )
    return observations


def gauge_payload_format(path: Path) -> str:
    text = path.read_text(encoding="utf-8").lstrip()
    if text.startswith("<"):
        return "xml"
    return "json"


def load_gauge_observations(
    path: Path,
    *,
    rainfall_keys: tuple[str, ...] = DEFAULT_RAINFALL_KEYS,
) -> list[GaugeObservation]:
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("<"):
        xml_windows = tuple(key for key in rainfall_keys if key.startswith("Past"))
        if not xml_windows:
            xml_windows = DEFAULT_XML_RAINFALL_WINDOWS
        return extract_gauge_observations_from_xml(text, rainfall_windows=xml_windows)
    payload = json.loads(text)
    return extract_gauge_observations(payload, rainfall_keys=rainfall_keys)


def qpe_grid_index_for_point(
    inspection: CwaGridInspection,
    *,
    latitude: float,
    longitude: float,
) -> tuple[int, int] | None:
    col = int(round((longitude - inspection.start_longitude) / inspection.grid_resolution))
    row = int(round((latitude - inspection.start_latitude) / inspection.grid_resolution))
    if row < 0 or col < 0:
        return None
    if row >= inspection.grid_dimension_y or col >= inspection.grid_dimension_x:
        return None
    return row, col


def qpe_value_at(
    inspection: CwaGridInspection,
    values: list[float],
    *,
    latitude: float,
    longitude: float,
) -> tuple[float | None, int | None, int | None, str]:
    index = qpe_grid_index_for_point(inspection, latitude=latitude, longitude=longitude)
    if index is None:
        return None, None, None, "outside_qpe_grid"
    row, col = index
    flat_index = row * inspection.grid_dimension_x + col
    if flat_index >= len(values):
        return None, row, col, "qpe_value_missing"
    qpe_mm = float(values[flat_index])
    if qpe_mm in inspection.nodata_values or qpe_mm < 0:
        return None, row, col, "qpe_nodata"
    return qpe_mm, row, col, ""


def match_qpe_to_gauges(
    *,
    inspection: CwaGridInspection,
    values: list[float],
    gauges: list[GaugeObservation],
) -> list[QpeGaugeMatch]:
    matches: list[QpeGaugeMatch] = []
    for gauge in gauges:
        qpe_mm, row, col, reason = qpe_value_at(
            inspection,
            values,
            latitude=gauge.latitude,
            longitude=gauge.longitude,
        )
        if qpe_mm is None:
            matches.append(
                QpeGaugeMatch(
                    station_id=gauge.station_id,
                    station_name=gauge.station_name,
                    latitude=gauge.latitude,
                    longitude=gauge.longitude,
                    gauge_mm=gauge.rainfall_mm,
                    qpe_mm=None,
                    difference_mm=None,
                    absolute_error_mm=None,
                    grid_row=row,
                    grid_col=col,
                    status="excluded",
                    reason=reason,
                )
            )
            continue
        difference = qpe_mm - gauge.rainfall_mm
        matches.append(
            QpeGaugeMatch(
                station_id=gauge.station_id,
                station_name=gauge.station_name,
                latitude=gauge.latitude,
                longitude=gauge.longitude,
                gauge_mm=gauge.rainfall_mm,
                qpe_mm=qpe_mm,
                difference_mm=round(difference, 6),
                absolute_error_mm=round(abs(difference), 6),
                grid_row=row,
                grid_col=col,
                status="matched",
            )
        )
    return matches


def summarize_matches(matches: list[QpeGaugeMatch]) -> dict[str, object]:
    matched = [match for match in matches if match.status == "matched" and match.qpe_mm is not None]
    excluded_reasons: dict[str, int] = {}
    for match in matches:
        if match.status != "excluded":
            continue
        excluded_reasons[match.reason] = excluded_reasons.get(match.reason, 0) + 1
    if not matched:
        return {
            "status": "no_matches",
            "gauge_count": len(matches),
            "matched_gauge_count": 0,
            "excluded_gauge_count": len(matches),
            "excluded_reasons": excluded_reasons,
            "mae_mm": None,
            "rmse_mm": None,
            "bias_mm": None,
            "correlation": None,
        }
    gauge = np.asarray([match.gauge_mm for match in matched], dtype=float)
    qpe = np.asarray([match.qpe_mm for match in matched], dtype=float)
    correlation: float | None
    if matched and len(matched) > 1 and np.std(gauge) > 0 and np.std(qpe) > 0:
        correlation = round(float(np.corrcoef(qpe, gauge)[0, 1]), 6)
    else:
        correlation = None
    return {
        "status": "ok",
        "gauge_count": len(matches),
        "matched_gauge_count": len(matched),
        "excluded_gauge_count": len(matches) - len(matched),
        "excluded_reasons": excluded_reasons,
        "mae_mm": round(float(np.mean(np.abs(qpe - gauge))), 6),
        "rmse_mm": round(rmse(qpe, gauge), 6),
        "bias_mm": round(float(np.mean(qpe - gauge)), 6),
        "correlation": correlation,
    }


def build_qpe_gauge_report(
    *,
    qpe_grid_path: Path,
    gauge_json_path: Path,
    event_id: str,
    rainfall_keys: tuple[str, ...] = DEFAULT_RAINFALL_KEYS,
) -> dict[str, object]:
    inspection, values = extract_cwa_grid_values(qpe_grid_path)
    gauges = load_gauge_observations(gauge_json_path, rainfall_keys=rainfall_keys)
    matches = match_qpe_to_gauges(inspection=inspection, values=values, gauges=gauges)
    summary = summarize_matches(matches)
    return {
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "event_id": event_id,
        "qpe_source": {
            "path": str(qpe_grid_path),
            "data_id": inspection.data_id,
            "data_time": inspection.data_time,
            "units": inspection.units,
            "grid_dimension_x": inspection.grid_dimension_x,
            "grid_dimension_y": inspection.grid_dimension_y,
            "grid_resolution": inspection.grid_resolution,
            "crs": inspection.crs,
            "nodata_values": list(inspection.nodata_values),
        },
        "gauge_source": {
            "path": str(gauge_json_path),
            "rainfall_keys": list(rainfall_keys),
            "format": gauge_payload_format(gauge_json_path),
            "source_data_id": "O-A0002-001",
        },
        "summary": summary,
        "matches": [match.to_dict() for match in matches],
        "notes": [
            "Nearest-grid lookup is used for the first validation pass.",
            "CWA QPE grids are estimates and must be checked against gauges before flood-risk use.",
        ],
    }


def write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate CWA QPE grid values against gauges.")
    parser.add_argument("--qpe-grid", type=Path, required=True)
    parser.add_argument("--gauge-json", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument(
        "--rainfall-key",
        action="append",
        dest="rainfall_keys",
        default=[],
        help="Gauge rainfall key to scan. Defaults to common CWA 1-hour rainfall names.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/qpe_gauge_validation.json"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    rainfall_keys = tuple(args.rainfall_keys) if args.rainfall_keys else DEFAULT_RAINFALL_KEYS
    report = build_qpe_gauge_report(
        qpe_grid_path=args.qpe_grid,
        gauge_json_path=args.gauge_json,
        event_id=args.event_id,
        rainfall_keys=rainfall_keys,
    )
    write_report(args.output, report)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status=str(report["summary"]["status"]),
        started_at=started_at,
        start_timer=start_timer,
        inputs={"qpe_grid": str(args.qpe_grid), "gauge_json": str(args.gauge_json)},
        outputs={"report": str(args.output)},
        row_counts={
            "gauges": int(report["summary"]["gauge_count"]),
            "matched_gauges": int(report["summary"]["matched_gauge_count"]),
        },
        metrics={
            "mae_mm": report["summary"]["mae_mm"],
            "rmse_mm": report["summary"]["rmse_mm"],
            "bias_mm": report["summary"]["bias_mm"],
        },
        metadata={"event_id": args.event_id, "rainfall_keys": list(rainfall_keys)},
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote QPE/gauge validation report to {args.output}")


if __name__ == "__main__":
    main()
