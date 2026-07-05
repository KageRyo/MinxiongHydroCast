"""Run a local demo data pipeline."""

from __future__ import annotations

from pathlib import Path

from floodcasttw.ingestion.hydrological_data import run_demo as run_hydrology_demo
from floodcasttw.ingestion.rainfall_alerts import run as run_rainfall_alerts


def main() -> None:
    output_dir = Path("data/processed")
    run_rainfall_alerts(
        output=output_dir / "rainfall_alerts.csv",
        mode="demo",
        county="10010",
        headed=False,
        timeout=45_000,
    )
    run_hydrology_demo(
        output_rain=output_dir / "rain_monitor.csv",
        output_flood=output_dir / "flood_sensors.csv",
    )
    print("[OK] Demo pipeline finished.")
