"""Scheduled operational collection for Minxiong observations and alerts."""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from floodcastminxiong.config import get_settings
from floodcastminxiong.ingestion import hydrological_data, rainfall_alerts
from floodcastminxiong.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    now_taipei_iso,
    record_run,
    start_run,
)
from floodcastminxiong.operations.health import aggregate_health, assess_dataset
from floodcastminxiong.operations.locations import (
    OPERATIONAL_LOCATION_FIELDS,
    build_operational_locations,
)
from floodcastminxiong.operations.features import (
    MINXIONG_FEATURE_FIELDS,
    build_minxiong_feature,
)
from floodcastminxiong.operations.snapshot_store import DatasetPayload, SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
PIPELINE_NAME = "operational_observations"
DEFAULT_STORE = get_settings().operations_store

DATASET_CONFIG = {
    "rainfall_alerts": {
        "product_type": "official_alert",
        "fieldnames": rainfall_alerts.FIELDNAMES,
        "timestamp_field": "抓取時間",
    },
    "rain_gauges": {
        "product_type": "official_observation",
        "fieldnames": hydrological_data.RAIN_FIELDNAMES,
        "timestamp_field": "水情時間ISO",
    },
    "flood_sensors": {
        "product_type": "official_observation",
        "fieldnames": hydrological_data.FLOOD_FIELDNAMES,
        "timestamp_field": "水情時間ISO",
    },
    "minxiong_features": {
        "product_type": "derived_feature",
        "fieldnames": MINXIONG_FEATURE_FIELDS,
        "timestamp_field": "feature_time",
    },
    "location_reference": {
        "product_type": "derived_reference",
        "fieldnames": OPERATIONAL_LOCATION_FIELDS,
        "timestamp_field": "snapshot_time",
    },
}


def collect_records(
    *,
    mode: str,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
) -> dict[str, list[dict[str, str]]]:
    if mode == "demo":
        alerts = rainfall_alerts.demo_records()
        rain, flood = hydrological_data.demo_records()
    elif mode == "live":
        alerts = rainfall_alerts.scrape_with_playwright(
            county_value=county,
            headless=not headed,
            timeout=timeout,
        )
        rain, flood = hydrological_data.scrape_live(
            county=county,
            headless=not headed,
            timeout=timeout,
            debug_dir=debug_dir,
        )
    else:
        raise ValueError(f"unsupported mode: {mode}")

    alert_report = rainfall_alerts.validate_rainfall_alert_records(
        alerts,
        allow_demo=mode == "demo",
    )
    rain_report, flood_report = hydrological_data.validate_hydrology_records(
        rain,
        flood,
        allow_demo=mode == "demo",
    )
    errors = [
        *alert_report.errors,
        *rain_report.errors,
        *flood_report.errors,
    ]
    if errors:
        raise ValueError("; ".join(errors))
    return {
        "rainfall_alerts": alerts,
        "rain_gauges": rain,
        "flood_sensors": flood,
    }


def build_payloads(
    records: dict[str, list[dict[str, str]]],
    *,
    mode: str,
    max_age_minutes: float,
    now: datetime,
) -> list[DatasetPayload]:
    payloads: list[DatasetPayload] = []
    for name, dataset_records in records.items():
        config = DATASET_CONFIG[name]
        fieldnames = list(config["fieldnames"])
        health = assess_dataset(
            dataset_records,
            fieldnames=fieldnames,
            timestamp_field=str(config["timestamp_field"]),
            mode=mode,
            max_age_minutes=max_age_minutes,
            now=now,
        )
        payloads.append(
            DatasetPayload(
                name=name,
                product_type=(
                    "demo_fixture" if mode == "demo" else str(config["product_type"])
                ),
                records=dataset_records,
                fieldnames=fieldnames,
                health=health,
            )
        )
    upstream_health = {
        payload.name: str(payload.health["state"])
        for payload in payloads
    }
    feature_records = [
        build_minxiong_feature(
            records,
            mode=mode,
            upstream_health=upstream_health,
            now=now,
        )
    ]
    feature_health = assess_dataset(
        feature_records,
        fieldnames=MINXIONG_FEATURE_FIELDS,
        timestamp_field="feature_time",
        mode=mode,
        max_age_minutes=max_age_minutes,
        now=now,
    )
    if mode == "live" and not all(
        state == "healthy" for state in upstream_health.values()
    ):
        feature_health["state"] = "upstream_unhealthy"
        feature_health["ready"] = False
    payloads.append(
        DatasetPayload(
            name="minxiong_features",
            product_type=(
                "demo_fixture"
                if mode == "demo"
                else str(DATASET_CONFIG["minxiong_features"]["product_type"])
            ),
            records=feature_records,
            fieldnames=MINXIONG_FEATURE_FIELDS,
            health=feature_health,
        )
    )
    return payloads


def run_collection(
    store: SnapshotStore,
    *,
    mode: str,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
    max_age_minutes: float,
    summary_output: Path | None,
    log_output: Path | None,
    now: datetime | None = None,
    pumping_stations: Path | None = None,
    shelters: Path | None = None,
    flood_risk_areas: Path | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(TAIPEI_TZ)
    started_at, start_timer = start_run()
    with store.collection_lock():
        try:
            records = collect_records(
                mode=mode,
                county=county,
                headed=headed,
                timeout=timeout,
                debug_dir=debug_dir,
            )
            records["location_reference"] = build_operational_locations(
                records,
                mode=mode,
                now=now,
                pumping_stations=pumping_stations,
                shelters=shelters,
                flood_risk_areas=flood_risk_areas,
            )
            payloads = build_payloads(
                records,
                mode=mode,
                max_age_minutes=max_age_minutes,
                now=now,
            )
            dataset_details = {
                payload.name: {"health": payload.health}
                for payload in payloads
            }
            health = aggregate_health(dataset_details, mode=mode)
            completed_at = now_taipei_iso()
            manifest = store.publish(
                mode=mode,
                started_at=started_at,
                completed_at=completed_at,
                datasets=payloads,
                health=health,
                metadata={
                    "county": county,
                    "source_authority": (
                        "demo fixture"
                        if mode == "demo"
                        else "Water Resources Agency, Taiwan"
                    ),
                    "experimental_forecast_included": False,
                    "static_location_inputs": {
                        "pumping_stations": str(pumping_stations)
                        if pumping_stations
                        else "",
                        "shelters": str(shelters) if shelters else "",
                        "flood_risk_areas": str(flood_risk_areas)
                        if flood_risk_areas
                        else "",
                    },
                },
                now=now,
            )
            summary = build_run_summary(
                pipeline=PIPELINE_NAME,
                status="ok",
                started_at=started_at,
                start_timer=start_timer,
                mode=mode,
                inputs={"county": county},
                outputs={
                    "snapshot_id": manifest["snapshot_id"],
                    "store": str(store.root),
                },
                row_counts={
                    payload.name: len(payload.records)
                    for payload in payloads
                },
                validation=health,
                metadata={"max_age_minutes": max_age_minutes},
            )
            record_run(
                summary_output=summary_output,
                log_output=log_output,
                summary=summary,
            )
            return manifest
        except Exception as exc:
            completed_at = now_taipei_iso()
            manifest = store.publish_failure(
                mode=mode,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason=str(exc),
                metadata={"county": county},
                now=now,
            )
            summary = build_run_summary(
                pipeline=PIPELINE_NAME,
                status="error",
                failure_reason=str(exc),
                started_at=started_at,
                start_timer=start_timer,
                mode=mode,
                inputs={"county": county},
                outputs={
                    "snapshot_id": manifest["snapshot_id"],
                    "store": str(store.root),
                },
            )
            record_run(
                summary_output=summary_output,
                log_output=log_output,
                summary=summary,
            )
            raise


def run_scheduler(
    store: SnapshotStore,
    *,
    interval_seconds: int | None,
    retention_days: int,
    **collection_options: Any,
) -> dict[str, Any] | None:
    if interval_seconds is not None and interval_seconds < 30:
        raise ValueError("interval_seconds must be at least 30")
    last_manifest: dict[str, Any] | None = None
    while True:
        try:
            last_manifest = run_collection(store, **collection_options)
            print(
                f"[OK] Snapshot {last_manifest['snapshot_id']} "
                f"health={last_manifest['health']['state']}"
            )
        except Exception as exc:
            print(f"[ERROR] Operational collection failed: {exc}")
            if interval_seconds is None:
                raise
        removed = store.prune(retention_days=retention_days)
        if removed:
            print(f"[INFO] Pruned {len(removed)} expired snapshots.")
        if interval_seconds is None:
            return last_manifest
        time.sleep(interval_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect and version Minxiong operational observations.",
    )
    parser.add_argument("--mode", choices=["live", "demo"], default="live")
    parser.add_argument("--county", default=hydrological_data.DEFAULT_COUNTY_VALUE)
    schedule = parser.add_mutually_exclusive_group()
    schedule.add_argument("--once", action="store_true", help="Run once and exit (default).")
    schedule.add_argument(
        "--interval-seconds",
        type=int,
        help="Run continuously at this interval; minimum 30 seconds.",
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=get_settings().operations_max_age_minutes,
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout", type=int, default=45_000)
    parser.add_argument("--debug-dir", type=Path, default=Path("data/raw/debug"))
    parser.add_argument("--pumping-stations", type=Path)
    parser.add_argument("--shelters", type=Path)
    parser.add_argument("--flood-risk-areas", type=Path)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    try:
        manifest = run_scheduler(
            SnapshotStore(args.store),
            interval_seconds=args.interval_seconds,
            retention_days=args.retention_days,
            mode=args.mode,
            county=args.county,
            headed=args.headed,
            timeout=args.timeout,
            debug_dir=args.debug_dir,
            max_age_minutes=args.max_age_minutes,
            summary_output=args.summary_output,
            log_output=args.log_output,
            pumping_stations=args.pumping_stations,
            shelters=args.shelters,
            flood_risk_areas=args.flood_risk_areas,
        )
    except KeyboardInterrupt:
        print("[INFO] Scheduler stopped.")
        return
    except Exception as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc

    if manifest and args.mode == "live" and not manifest["health"]["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
