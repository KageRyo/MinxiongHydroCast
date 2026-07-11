"""Build a unified location reference table from processed CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.spatial.locations import (
    build_location_reference,
    read_csv_records,
    write_location_reference,
)

PIPELINE_NAME = "location_reference"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FloodCastMinxiong location references.")
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
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
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
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={
            "rain": str(args.rain),
            "flood": str(args.flood),
            "pumping_stations": str(args.pumping_stations) if args.pumping_stations else "",
            "shelters": str(args.shelters) if args.shelters else "",
            "flood_risk_areas": str(args.flood_risk_areas) if args.flood_risk_areas else "",
        },
        outputs={"location_reference": str(args.output)},
        row_counts={"locations": count},
    )
    record_run(
        summary_output=args.summary_output,
        log_output=args.log_output,
        summary=summary,
    )
    print(f"[OK] Wrote {count} location records to {args.output}")


if __name__ == "__main__":
    main()
