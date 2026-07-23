"""Scheduled operational collection for Minxiong observations and alerts."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion import hydrological_data, rainfall_alerts
from minxionghydrocast.ingestion.cwa_rainfall_api import CwaRainGaugeAdapter
from minxionghydrocast.ingestion.http_client import close_verified_session
from minxionghydrocast.ingestion.source_adapter import (
    SourceAdapter,
    SourceAdapterError,
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceRetryMetrics,
    SourceSchemaError,
    records_sha256,
)
from minxionghydrocast.ingestion.wra_flood_sensor_api import WraFloodSensorAdapter
from minxionghydrocast.ingestion.wra_rainfall_alert_api import WraRainfallAlertAdapter
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    now_taipei_iso,
    record_run,
    start_run,
)
from minxionghydrocast.operations.health import aggregate_health, assess_dataset
from minxionghydrocast.operations.locations import (
    OPERATIONAL_LOCATION_FIELDS,
    build_operational_locations,
)
from minxionghydrocast.operations.features import (
    MINXIONG_FEATURE_FIELDS,
    build_minxiong_feature,
)
from minxionghydrocast.operations.snapshot_store import DatasetPayload, SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
PIPELINE_NAME = "operational_observations"
DEFAULT_STORE = get_settings().operations_store

DATASET_CONFIG = {
    "rainfall_alerts": {
        "product_type": "official_alert",
        "fieldnames": rainfall_alerts.FIELDNAMES,
        "timestamp_field": "水情時間ISO",
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


@dataclass
class OperationalCollection:
    records: dict[str, list[dict[str, str]]]
    sources: dict[str, SourceProvenance]
    source_retries: dict[str, SourceRetryMetrics] = field(default_factory=dict)


def _record_fetched_at(records: list[dict[str, str]]) -> str:
    return records[0].get("抓取時間", "") if records else now_taipei_iso()


def _fixture_source(dataset: str, records: list[dict[str, str]]) -> SourceProvenance:
    return SourceProvenance(
        source_kind="demo_fixture",
        outcome="ok",
        authority="MinxiongHydroCast",
        dataset_id=f"demo-{dataset}",
        source_url=f"demo://{dataset}",
        fetched_at=_record_fetched_at(records),
        schema_version=f"{dataset}-demo-v1",
        content_sha256=records_sha256(records),
    )


def _scraper_source(
    dataset: str,
    records: list[dict[str, str]],
    *,
    source_url: str,
    fallback_error: SourceRequestError | None = None,
) -> SourceProvenance:
    return SourceProvenance(
        source_kind="scraper_fallback",
        outcome="fallback",
        authority="Water Resources Agency, Taiwan",
        dataset_id=f"wra-fhy-{dataset}",
        source_url=source_url,
        fetched_at=_record_fetched_at(records),
        schema_version=f"wra-fhy-{dataset}-page-v1",
        content_sha256=records_sha256(records),
        fallback_reason_kind=fallback_error.kind if fallback_error else None,
        fallback_reason=(
            str(fallback_error) if fallback_error else "scraper source explicitly selected"
        ),
    )


def _derived_source(
    dataset: str,
    records: list[dict[str, str]],
    *,
    inputs: dict[str, SourceProvenance],
    now: datetime,
) -> SourceProvenance:
    input_sources = list(inputs.values())
    if input_sources and all(source.source_kind == "demo_fixture" for source in input_sources):
        source_kind = "demo_fixture"
        outcome = "ok"
    elif any(source.source_kind == "scraper_fallback" for source in input_sources):
        source_kind = "scraper_fallback"
        outcome = "fallback"
    else:
        source_kind = "api"
        outcome = "stale" if any(source.outcome == "stale" for source in input_sources) else "ok"
    fallback_datasets = sorted(
        name for name, source in inputs.items() if source.source_kind == "scraper_fallback"
    )
    return SourceProvenance(
        source_kind=source_kind,
        outcome=outcome,
        authority="MinxiongHydroCast",
        dataset_id=f"derived-{dataset}",
        source_url=f"snapshot-derived://{dataset}",
        fetched_at=now.isoformat(timespec="seconds"),
        schema_version=f"{dataset}-v1",
        content_sha256=records_sha256(records),
        fallback_reason=(
            f"derived from scraper fallback datasets: {', '.join(fallback_datasets)}"
            if fallback_datasets
            else None
        ),
    )


def _check_adapter_result(
    result: SourceResult,
    *,
    dataset: str,
) -> tuple[list[dict[str, str]], SourceProvenance, SourceRetryMetrics]:
    if result.dataset != dataset:
        raise SourceSchemaError(
            "schema_drift",
            f"source adapter returned unexpected dataset: {result.dataset}",
        )
    return result.records, result.provenance, result.retry_metrics


def _collect_alerts(
    *,
    source: str,
    county: str,
    headed: bool,
    timeout: int,
    api_timeout_seconds: float,
    max_age_minutes: float,
    adapter: SourceAdapter | None,
    now: datetime | None,
) -> tuple[list[dict[str, str]], SourceProvenance, SourceRetryMetrics]:
    settings = get_settings()
    fallback_error: SourceRequestError | None = None
    retry_metrics = SourceRetryMetrics()
    if source != "scraper":
        official_adapter = adapter or WraRainfallAlertAdapter(
            api_key=settings.wra_api_key,
            county_code=county,
            base_url=settings.wra_api_url,
            timeout_seconds=api_timeout_seconds,
            max_age_minutes=max_age_minutes,
            now=now,
        )
        try:
            return _check_adapter_result(official_adapter.collect(), dataset="rainfall_alerts")
        except SourceRequestError as exc:
            if source == "api":
                raise
            fallback_error = exc
            retry_metrics = exc.retry_metrics

    records = rainfall_alerts.scrape_with_playwright(
        county_value=county,
        headless=not headed,
        timeout=timeout,
    )
    if not records:
        raise SourceAdapterError(
            "empty_unexpected",
            "WRA rainfall alert scraper returned no records",
        )
    return (
        records,
        _scraper_source(
            "rainfall_alerts",
            records,
            source_url=f"{settings.wra_base_url.rstrip('/')}/service/alertQuery#",
            fallback_error=fallback_error,
        ),
        retry_metrics,
    )


def _collect_rain_gauges(
    *,
    source: str,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
    api_timeout_seconds: float,
    max_age_minutes: float,
    adapter: SourceAdapter | None,
    now: datetime | None,
) -> tuple[list[dict[str, str]], SourceProvenance, SourceRetryMetrics]:
    settings = get_settings()
    fallback_error: SourceRequestError | None = None
    retry_metrics = SourceRetryMetrics()
    if source != "scraper":
        official_adapter = adapter or CwaRainGaugeAdapter(
            authorization=settings.cwa_api_key,
            county_code=county,
            timeout_seconds=api_timeout_seconds,
            max_age_minutes=max_age_minutes,
            now=now,
        )
        try:
            return _check_adapter_result(official_adapter.collect(), dataset="rain_gauges")
        except SourceRequestError as exc:
            if source == "api":
                raise
            fallback_error = exc
            retry_metrics = exc.retry_metrics

    records = hydrological_data.scrape_rain_live(
        county=county,
        headless=not headed,
        timeout=timeout,
        debug_dir=debug_dir,
    )
    if not records:
        raise SourceAdapterError(
            "empty_unexpected",
            "WRA rain-gauge scraper returned no records",
        )
    return (
        records,
        _scraper_source(
            "rain_gauges",
            records,
            source_url=f"{settings.wra_base_url}{hydrological_data.RAIN_PATH}",
            fallback_error=fallback_error,
        ),
        retry_metrics,
    )


def _collect_flood_sensors(
    *,
    source: str,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
    api_timeout_seconds: float,
    max_age_minutes: float,
    adapter: SourceAdapter | None,
    now: datetime | None,
) -> tuple[list[dict[str, str]], SourceProvenance, SourceRetryMetrics]:
    settings = get_settings()
    fallback_error: SourceRequestError | None = None
    retry_metrics = SourceRetryMetrics()
    if source != "scraper":
        official_adapter = adapter or WraFloodSensorAdapter(
            county_code=county,
            base_url=settings.wra_open_data_api_url,
            timeout_seconds=api_timeout_seconds,
            max_age_minutes=max_age_minutes,
            now=now,
        )
        try:
            return _check_adapter_result(official_adapter.collect(), dataset="flood_sensors")
        except SourceRequestError as exc:
            if source == "api":
                raise
            fallback_error = exc
            retry_metrics = exc.retry_metrics

    records = hydrological_data.scrape_flood_live(
        county=county,
        headless=not headed,
        timeout=timeout,
        debug_dir=debug_dir,
    )
    if not records:
        raise SourceAdapterError(
            "empty_unexpected",
            "WRA flood-sensor scraper returned no records",
        )
    return (
        records,
        _scraper_source(
            "flood_sensors",
            records,
            source_url=f"{settings.wra_base_url}{hydrological_data.FLOOD_SENSOR_PATH}",
            fallback_error=fallback_error,
        ),
        retry_metrics,
    )


def collect_records(
    *,
    mode: str,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
    alert_source: str = "auto",
    rain_source: str = "auto",
    flood_source: str = "auto",
    api_timeout_seconds: float = 30,
    max_age_minutes: float = 30,
    flood_max_age_minutes: float = 90,
    alert_adapter: SourceAdapter | None = None,
    rain_adapter: SourceAdapter | None = None,
    flood_adapter: SourceAdapter | None = None,
    now: datetime | None = None,
) -> OperationalCollection:
    source_options = {
        "alert": alert_source,
        "rain": rain_source,
        "flood": flood_source,
    }
    for name, source in source_options.items():
        if source not in {"api", "auto", "scraper"}:
            raise ValueError(f"unsupported {name} source: {source}")
    if max_age_minutes <= 0 or flood_max_age_minutes <= 0:
        raise ValueError("freshness limits must be positive")
    if mode == "demo":
        alerts = rainfall_alerts.demo_records()
        rain, flood = hydrological_data.demo_records()
        sources = {
            "rainfall_alerts": _fixture_source("rainfall_alerts", alerts),
            "rain_gauges": _fixture_source("rain_gauges", rain),
            "flood_sensors": _fixture_source("flood_sensors", flood),
        }
        source_retries = {
            name: SourceRetryMetrics()
            for name in ("rainfall_alerts", "rain_gauges", "flood_sensors")
        }
    elif mode == "live":
        alerts, alert_provenance, alert_retries = _collect_alerts(
            source=alert_source,
            county=county,
            headed=headed,
            timeout=timeout,
            api_timeout_seconds=api_timeout_seconds,
            max_age_minutes=max_age_minutes,
            adapter=alert_adapter,
            now=now,
        )
        rain, rain_provenance, rain_retries = _collect_rain_gauges(
            source=rain_source,
            county=county,
            headed=headed,
            timeout=timeout,
            debug_dir=debug_dir,
            api_timeout_seconds=api_timeout_seconds,
            max_age_minutes=max_age_minutes,
            adapter=rain_adapter,
            now=now,
        )
        flood, flood_provenance, flood_retries = _collect_flood_sensors(
            source=flood_source,
            county=county,
            headed=headed,
            timeout=timeout,
            debug_dir=debug_dir,
            api_timeout_seconds=api_timeout_seconds,
            max_age_minutes=flood_max_age_minutes,
            adapter=flood_adapter,
            now=now,
        )
        sources = {
            "rainfall_alerts": alert_provenance,
            "rain_gauges": rain_provenance,
            "flood_sensors": flood_provenance,
        }
        source_retries = {
            "rainfall_alerts": alert_retries,
            "rain_gauges": rain_retries,
            "flood_sensors": flood_retries,
        }
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
    return OperationalCollection(
        records={
            "rainfall_alerts": alerts,
            "rain_gauges": rain,
            "flood_sensors": flood,
        },
        sources=sources,
        source_retries=source_retries,
    )


def build_payloads(
    records: dict[str, list[dict[str, str]]],
    *,
    sources: dict[str, SourceProvenance],
    mode: str,
    max_age_minutes: float,
    flood_max_age_minutes: float | None = None,
    now: datetime,
) -> list[DatasetPayload]:
    payloads: list[DatasetPayload] = []
    for name, dataset_records in records.items():
        config = DATASET_CONFIG[name]
        fieldnames = list(config["fieldnames"])
        source = sources[name]
        timestamp_field = str(config["timestamp_field"])
        if name == "rainfall_alerts" and source.source_kind != "api":
            timestamp_field = "抓取時間"
        dataset_max_age = (
            flood_max_age_minutes
            if name == "flood_sensors" and flood_max_age_minutes is not None
            else max_age_minutes
        )
        freshness_observed_at: str | None = None
        if name == "flood_sensors" and dataset_records:
            active_timestamps = [
                timestamp
                for record in dataset_records
                if (timestamp := record.get("水情時間ISO", "").strip())
                if record.get("啟用狀態", "true").strip().lower() != "false"
            ]
            freshness_observed_at = max(active_timestamps) if active_timestamps else None
        health = assess_dataset(
            dataset_records,
            fieldnames=fieldnames,
            timestamp_field=timestamp_field,
            mode=mode,
            max_age_minutes=dataset_max_age,
            now=now,
            empty_observed_at=(
                source.fetched_at
                if name == "rainfall_alerts" and source.outcome == "empty"
                else None
            ),
            freshness_observed_at=freshness_observed_at,
        )
        if mode == "live" and source.outcome == "stale" and health["state"] == "healthy":
            health["state"] = "stale"
            health["ready"] = False
            health["persistent_state"] = "stale"
            health["degradation_reasons"] = ["source_stale"]
        if mode == "live" and source.source_kind == "scraper_fallback":
            health["degradation_reasons"] = ["scraper_fallback"]
            health["persistent_state"] = "degraded"
            if health["state"] == "healthy":
                health["state"] = "degraded"
                health["ready"] = False
        payloads.append(
            DatasetPayload(
                name=name,
                product_type=(
                    "demo_fixture" if mode == "demo" else str(config["product_type"])
                ),
                records=dataset_records,
                fieldnames=fieldnames,
                health=health,
                source=source.model_dump(exclude_none=True),
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
    feature_source = _derived_source(
        "minxiong_features",
        feature_records,
        inputs={
            name: sources[name]
            for name in ("rainfall_alerts", "rain_gauges", "flood_sensors")
        },
        now=now,
    )
    sources["minxiong_features"] = feature_source
    feature_health = assess_dataset(
        feature_records,
        fieldnames=MINXIONG_FEATURE_FIELDS,
        timestamp_field="feature_time",
        mode=mode,
        max_age_minutes=max_age_minutes,
        now=now,
    )
    unhealthy_upstreams = {
        name: state for name, state in upstream_health.items() if state != "healthy"
    }
    coverage_gaps = feature_records[0]["coverage_gaps"].split(";")
    coverage_gaps = [gap for gap in coverage_gaps if gap]
    if mode == "live" and unhealthy_upstreams:
        feature_health["state"] = "upstream_unhealthy"
        feature_health["ready"] = False
        feature_health["persistent_state"] = "upstream_unhealthy"
        feature_health["degradation_reasons"] = [
            *(
                f"{name}={state}"
                for name, state in sorted(unhealthy_upstreams.items())
            ),
            *(f"coverage:{gap}" for gap in coverage_gaps),
        ]
    elif mode == "live" and coverage_gaps:
        feature_health["state"] = "coverage_missing"
        feature_health["ready"] = False
        feature_health["persistent_state"] = "coverage_missing"
        feature_health["degradation_reasons"] = [
            f"coverage:{gap}" for gap in coverage_gaps
        ]
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
            source=feature_source.model_dump(exclude_none=True),
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
    alert_source: str = "auto",
    rain_source: str = "auto",
    flood_source: str = "auto",
    api_timeout_seconds: float = 30,
    flood_max_age_minutes: float = 90,
    alert_adapter: SourceAdapter | None = None,
    rain_adapter: SourceAdapter | None = None,
    flood_adapter: SourceAdapter | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(TAIPEI_TZ)
    started_at, start_timer = start_run()
    with store.collection_lock():
        source_retry_metrics: dict[str, dict[str, object]] = {}
        try:
            collection = collect_records(
                mode=mode,
                county=county,
                headed=headed,
                timeout=timeout,
                debug_dir=debug_dir,
                alert_source=alert_source,
                rain_source=rain_source,
                flood_source=flood_source,
                api_timeout_seconds=api_timeout_seconds,
                max_age_minutes=max_age_minutes,
                flood_max_age_minutes=flood_max_age_minutes,
                alert_adapter=alert_adapter,
                rain_adapter=rain_adapter,
                flood_adapter=flood_adapter,
                now=now,
            )
            source_retry_metrics = {
                name: retry_metrics.model_dump(mode="json")
                for name, retry_metrics in sorted(collection.source_retries.items())
            }
            source_retry_total = sum(
                retry_metrics.total
                for retry_metrics in collection.source_retries.values()
            )
            records = collection.records
            records["location_reference"] = build_operational_locations(
                records,
                mode=mode,
                now=now,
                pumping_stations=pumping_stations,
                shelters=shelters,
                flood_risk_areas=flood_risk_areas,
            )
            collection.sources["location_reference"] = _derived_source(
                "location_reference",
                records["location_reference"],
                inputs={
                    name: collection.sources[name]
                    for name in ("rain_gauges", "flood_sensors")
                },
                now=now,
            )
            payloads = build_payloads(
                records,
                sources=collection.sources,
                mode=mode,
                max_age_minutes=max_age_minutes,
                flood_max_age_minutes=flood_max_age_minutes,
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
                        else (
                            "Central Weather Administration and Water Resources Agency, Taiwan"
                        )
                    ),
                    "source_authorities": sorted(
                        {source.authority for source in collection.sources.values()}
                    ),
                    "source_kinds": {
                        name: source.source_kind
                        for name, source in sorted(collection.sources.items())
                    },
                    "source_retries": source_retry_metrics,
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
                metrics={
                    "source_retry_total": source_retry_total,
                    "source_retries": source_retry_metrics,
                },
                validation=health,
                metadata={
                    "max_age_minutes": max_age_minutes,
                    "flood_max_age_minutes": flood_max_age_minutes,
                    "alert_source": alert_source,
                    "rain_source": rain_source,
                    "flood_source": flood_source,
                    "source_kinds": {
                        name: source.source_kind
                        for name, source in sorted(collection.sources.items())
                    },
                },
            )
            record_run(
                summary_output=summary_output,
                log_output=log_output,
                summary=summary,
            )
            return manifest
        except Exception as exc:
            if isinstance(exc, SourceAdapterError):
                dataset = exc.dataset or "unknown"
                source_retry_metrics = {
                    dataset: exc.retry_metrics.model_dump(mode="json")
                }
            source_retry_total = sum(
                int(metrics.get("total", 0))
                for metrics in source_retry_metrics.values()
            )
            completed_at = now_taipei_iso()
            manifest = store.publish_failure(
                mode=mode,
                started_at=started_at,
                completed_at=completed_at,
                failure_reason=str(exc),
                metadata={
                    "county": county,
                    "failure_kind": (
                        exc.kind if isinstance(exc, SourceAdapterError) else "collection"
                    ),
                    "alert_source": alert_source,
                    "rain_source": rain_source,
                    "flood_source": flood_source,
                    "source_retries": source_retry_metrics,
                },
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
                metrics={
                    "source_retry_total": source_retry_total,
                    "source_retries": source_retry_metrics,
                },
                metadata={
                    "failure_kind": (
                        exc.kind if isinstance(exc, SourceAdapterError) else "collection"
                    ),
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
        "--alert-source",
        choices=["api", "auto", "scraper"],
        default="auto",
        help="WRA warning API selection; auto falls back only for request failures.",
    )
    parser.add_argument(
        "--rain-source",
        choices=["api", "auto", "scraper"],
        default="auto",
        help="CWA API selection; auto falls back only for request failures.",
    )
    parser.add_argument(
        "--flood-source",
        choices=["api", "auto", "scraper"],
        default="auto",
        help="WRA IoW API selection; auto falls back only for request failures.",
    )
    parser.add_argument("--api-timeout-seconds", type=float, default=30)
    parser.add_argument(
        "--max-age-minutes",
        type=float,
        default=get_settings().operations_max_age_minutes,
    )
    parser.add_argument(
        "--flood-max-age-minutes",
        type=float,
        default=get_settings().operations_flood_max_age_minutes,
        help="Freshness limit for the hourly WRA IoW Open Data snapshot.",
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
            alert_source=args.alert_source,
            rain_source=args.rain_source,
            flood_source=args.flood_source,
            api_timeout_seconds=args.api_timeout_seconds,
            flood_max_age_minutes=args.flood_max_age_minutes,
        )
    except KeyboardInterrupt:
        print("[INFO] Scheduler stopped.")
        return
    except Exception as exc:
        raise SystemExit(f"[ERROR] {exc}") from exc
    finally:
        close_verified_session()

    if manifest and args.mode == "live" and not manifest["health"]["ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
