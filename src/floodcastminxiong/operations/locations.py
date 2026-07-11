"""Build snapshot-aligned operational location references."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from floodcastminxiong.spatial.locations import (
    LOCATION_FIELDNAMES,
    build_location_reference,
    read_csv_records,
)

OPERATIONAL_LOCATION_FIELDS = [*LOCATION_FIELDNAMES, "snapshot_time", "data_mode"]


def build_operational_locations(
    records: dict[str, list[dict[str, str]]],
    *,
    mode: str,
    now: datetime,
    pumping_stations: Path | None = None,
    shelters: Path | None = None,
    flood_risk_areas: Path | None = None,
) -> list[dict[str, str]]:
    locations = build_location_reference(
        rain_records=records["rain_gauges"],
        flood_records=records["flood_sensors"],
        pumping_station_records=read_csv_records(pumping_stations)
        if pumping_stations
        else [],
        shelter_records=read_csv_records(shelters) if shelters else [],
        flood_risk_area_records=read_csv_records(flood_risk_areas)
        if flood_risk_areas
        else [],
    )
    snapshot_time = now.isoformat(timespec="seconds")
    return [
        {
            **location,
            "snapshot_time": snapshot_time,
            "data_mode": mode,
        }
        for location in locations
    ]
