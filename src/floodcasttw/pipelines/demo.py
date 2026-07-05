"""Run a local demo data pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodcasttw.ingestion.hydrological_data import run_demo as run_hydrology_demo
from floodcasttw.ingestion.rainfall_alerts import run as run_rainfall_alerts
from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "demo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local FloodCastTW demo pipeline.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    output_dir = args.output_dir
    rainfall_count = run_rainfall_alerts(
        output=output_dir / "rainfall_alerts.csv",
        mode="demo",
        county="10010",
        headed=False,
        timeout=45_000,
    )
    rain_count, flood_count = run_hydrology_demo(
        output_rain=output_dir / "rain_monitor.csv",
        output_flood=output_dir / "flood_sensors.csv",
    )
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        mode="demo",
        outputs={
            "rainfall_alerts": str(output_dir / "rainfall_alerts.csv"),
            "rain_monitor": str(output_dir / "rain_monitor.csv"),
            "flood_sensors": str(output_dir / "flood_sensors.csv"),
        },
        row_counts={
            "rainfall_alerts": rainfall_count,
            "rain_monitor": rain_count,
            "flood_sensors": flood_count,
        },
    )
    record_run(
        summary_output=args.summary_output,
        log_output=args.log_output,
        summary=summary,
    )
    print("[OK] Demo pipeline finished.")


if __name__ == "__main__":
    main()
