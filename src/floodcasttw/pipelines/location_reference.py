"""Build a unified location reference table from processed CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodcasttw.spatial.locations import (
    build_location_reference,
    read_csv_records,
    write_location_reference,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FloodCastTW location references.")
    parser.add_argument("--rain", type=Path, default=Path("data/processed/rain_monitor.csv"))
    parser.add_argument("--flood", type=Path, default=Path("data/processed/flood_sensors.csv"))
    parser.add_argument("--pumping-stations", type=Path, default=None)
    parser.add_argument("--shelters", type=Path, default=None)
    parser.add_argument("--flood-risk-areas", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/location_reference.csv"),
    )
    args = parser.parse_args()

    locations = build_location_reference(
        rain_records=read_csv_records(args.rain),
        flood_records=read_csv_records(args.flood),
        pumping_station_records=read_csv_records(args.pumping_stations)
        if args.pumping_stations
        else [],
        shelter_records=read_csv_records(args.shelters) if args.shelters else [],
        flood_risk_area_records=read_csv_records(args.flood_risk_areas)
        if args.flood_risk_areas
        else [],
    )
    count = write_location_reference(locations, args.output)
    print(f"[OK] Wrote {count} location records to {args.output}")


if __name__ == "__main__":
    main()
