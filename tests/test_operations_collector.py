import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.operations import collector
from minxionghydrocast.ingestion.source_adapter import (
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceRetryMetrics,
    SourceSchemaError,
    records_sha256,
)
from minxionghydrocast.operations.snapshot_store import SnapshotStore
from minxionghydrocast.operations.health import refresh_dataset_health

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def run_demo(store: SnapshotStore, tmp_path, now: datetime):
    return collector.run_collection(
        store,
        mode="demo",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        max_age_minutes=30,
        summary_output=tmp_path / "summary.json",
        log_output=tmp_path / "runs.jsonl",
        now=now,
    )


def test_demo_collection_writes_versioned_non_ready_snapshot(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)

    manifest = run_demo(store, tmp_path, now)

    assert manifest["mode"] == "demo"
    assert manifest["health"]["state"] == "demo"
    assert manifest["health"]["ready"] is False
    assert set(manifest["datasets"]) == {
        "rainfall_alerts",
        "rain_gauges",
        "flood_sensors",
        "minxiong_features",
        "location_reference",
    }
    assert manifest["datasets"]["rainfall_alerts"]["product_type"] == "demo_fixture"
    assert manifest["datasets"]["rain_gauges"]["product_type"] == "demo_fixture"
    assert manifest["datasets"]["rain_gauges"]["source"]["source_kind"] == "demo_fixture"
    assert manifest["datasets"]["rain_gauges"]["source"]["dataset_id"] == "demo-rain_gauges"
    feature = store.read_dataset(manifest, "minxiong_features")[0]
    assert feature["township"] == "民雄鄉"
    assert feature["rain_gauge_count"] == "1"
    assert feature["flood_sensor_count"] == "0"
    assert feature["rainfall_alert_count"] == "1"
    assert feature["qpe_available"] == "false"
    assert feature["data_ready"] == "false"
    locations = store.read_dataset(manifest, "location_reference")
    assert len(locations) == 4
    assert {location["source_type"] for location in locations} == {
        "rain_gauge",
        "flood_sensor",
    }
    assert manifest["metadata"]["source_authority"] == "demo fixture"
    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "runs.jsonl").exists()


def test_collection_failure_is_recorded_without_replacing_latest(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    latest = run_demo(store, tmp_path, now)

    def fail_collection(**_kwargs):
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(collector, "collect_records", fail_collection)
    with pytest.raises(RuntimeError, match="source unavailable"):
        run_demo(store, tmp_path, now + timedelta(minutes=10))

    assert store.read_latest()["snapshot_id"] == latest["snapshot_id"]
    assert store.read_latest_attempt()["status"] == "error"
    assert store.read_latest_attempt()["failure_reason"] == "source unavailable"


def test_schema_drift_failure_kind_is_recorded(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path / "operations")
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)

    def fail_collection(**_kwargs):
        raise SourceSchemaError(
            "schema_drift",
            "WRA contract changed",
            dataset="flood_sensors",
            retry_metrics=SourceRetryMetrics.from_counter(
                {("wra_join_transaction", "malformed_catalog"): 2}
            ),
        )

    monkeypatch.setattr(collector, "collect_records", fail_collection)
    with pytest.raises(SourceSchemaError, match="contract changed"):
        run_demo(store, tmp_path, now)

    attempt = store.read_latest_attempt()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert attempt["status"] == "error"
    assert attempt["metadata"]["failure_kind"] == "schema_drift"
    assert attempt["metadata"]["source_retries"]["flood_sensors"]["total"] == 2
    assert summary["metrics"]["source_retry_total"] == 2
    assert summary["metrics"]["source_retries"]["flood_sensors"]["counts"] == [
        {
            "source": "wra_join_transaction",
            "reason": "malformed_catalog",
            "count": 2,
        }
    ]


def test_live_payloads_use_official_product_classifications():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    collection = collector.collect_records(
        mode="demo",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
    )
    records = collection.records
    records["location_reference"] = collector.build_operational_locations(
        records,
        mode="live",
        now=now,
    )
    collection.sources["location_reference"] = collector._fixture_source(
        "location_reference",
        records["location_reference"],
    )

    payloads = collector.build_payloads(
        records,
        sources=collection.sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )

    assert {payload.name: payload.product_type for payload in payloads} == {
        "rainfall_alerts": "official_alert",
        "rain_gauges": "official_observation",
        "flood_sensors": "official_observation",
        "minxiong_features": "derived_feature",
        "location_reference": "derived_reference",
    }


def live_scraper_records(now: datetime):
    alerts = collector.rainfall_alerts.demo_records()
    rain, flood = collector.hydrological_data.demo_records()
    timestamp = now.isoformat(timespec="seconds")
    for record in alerts:
        record["資料模式"] = "live"
        record["抓取時間"] = timestamp
    for record in [*rain, *flood]:
        record["資料模式"] = "live"
        record["水情時間ISO"] = timestamp
        record["資料產出時間ISO"] = timestamp
        record["抓取時間"] = timestamp
        record["資料來源"] = "https://example.test/wra"
    return alerts, rain, flood


def add_minxiong_flood_coverage(flood: list[dict[str, str]]) -> None:
    flood[0].update(
        {
            "鄉鎮": "民雄鄉",
            "感測器名稱": "CYC136 民雄鄉大崎村淹水深度",
            "地址": "嘉義縣民雄鄉大崎村",
            "啟用狀態": "true",
        }
    )


def api_source(records: list[dict[str, str]], now: datetime) -> SourceProvenance:
    return SourceProvenance(
        source_kind="api",
        outcome="ok",
        authority="Central Weather Administration, Taiwan",
        dataset_id="O-A0002-001",
        source_url="https://example.test/O-A0002-001?Authorization=REDACTED",
        fetched_at=now.isoformat(timespec="seconds"),
        schema_version="cwa-o-a0002-001-v1",
        content_sha256=records_sha256(records),
    )


def wra_api_source(
    dataset: str,
    records: list[dict[str, str]],
    now: datetime,
    *,
    outcome: str = "ok",
) -> SourceProvenance:
    return SourceProvenance(
        source_kind="api",
        outcome=outcome,
        authority="Water Resources Agency, Taiwan",
        dataset_id=f"wra-{dataset}",
        source_url=f"https://example.test/{dataset}",
        fetched_at=now.isoformat(timespec="seconds"),
        schema_version=f"{dataset}-v1",
        content_sha256=records_sha256(records),
    )


def test_live_collection_accepts_official_empty_alert_and_api_flood_sensor(monkeypatch):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    _alerts, rain, flood = live_scraper_records(now)

    class AlertAdapter:
        dataset = "rainfall_alerts"

        def collect(self):
            return SourceResult(
                "rainfall_alerts",
                [],
                wra_api_source("rainfall_alerts", [], now, outcome="empty"),
            )

    class RainAdapter:
        dataset = "rain_gauges"

        def collect(self):
            return SourceResult("rain_gauges", rain, api_source(rain, now))

    class FloodAdapter:
        dataset = "flood_sensors"

        def collect(self):
            return SourceResult(
                "flood_sensors",
                flood,
                wra_api_source("flood_sensors", flood, now),
            )

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: pytest.fail("valid empty API response must not use fallback"),
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_rain_live",
        lambda **_kwargs: pytest.fail("rain API success must not use fallback"),
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_flood_live",
        lambda **_kwargs: pytest.fail("flood API success must not use fallback"),
    )

    collection = collector.collect_records(
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        alert_source="api",
        rain_source="api",
        flood_source="api",
        alert_adapter=AlertAdapter(),
        rain_adapter=RainAdapter(),
        flood_adapter=FloodAdapter(),
        now=now,
    )

    assert collection.records["rainfall_alerts"] == []
    assert collection.sources["rainfall_alerts"].outcome == "empty"
    assert collection.sources["flood_sensors"].source_kind == "api"


def test_valid_empty_alert_is_healthy_and_keeps_feature_ready():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    _alerts, rain, flood = live_scraper_records(now)
    add_minxiong_flood_coverage(flood)
    records = {
        "rainfall_alerts": [],
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        "rainfall_alerts": wra_api_source(
            "rainfall_alerts",
            [],
            now,
            outcome="empty",
        ),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source("flood_sensors", flood, now),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        flood_max_age_minutes=90,
        now=now,
    )

    alert_payload = next(payload for payload in payloads if payload.name == "rainfall_alerts")
    feature_payload = next(payload for payload in payloads if payload.name == "minxiong_features")
    assert alert_payload.records == []
    assert alert_payload.health["state"] == "healthy"
    assert alert_payload.health["ready"] is True
    assert feature_payload.records[0]["rainfall_alert_count"] == "0"
    assert feature_payload.records[0]["coverage_ready"] == "true"
    assert feature_payload.health["state"] == "healthy"


def test_live_snapshot_with_empty_official_alert_can_be_globally_ready(
    tmp_path,
    monkeypatch,
):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    _alerts, rain, flood = live_scraper_records(now)
    add_minxiong_flood_coverage(flood)
    collection = collector.OperationalCollection(
        records={
            "rainfall_alerts": [],
            "rain_gauges": rain,
            "flood_sensors": flood,
        },
        sources={
            "rainfall_alerts": wra_api_source(
                "rainfall_alerts",
                [],
                now,
                outcome="empty",
            ),
            "rain_gauges": api_source(rain, now),
            "flood_sensors": wra_api_source("flood_sensors", flood, now),
        },
        source_retries={
            "flood_sensors": SourceRetryMetrics.from_counter(
                {
                    ("official_http", "invalid_json"): 1,
                    ("wra_join_transaction", "missing_sensor_metadata"): 1,
                }
            )
        },
    )
    monkeypatch.setattr(collector, "collect_records", lambda **_kwargs: collection)
    store = SnapshotStore(tmp_path / "operations")

    manifest = collector.run_collection(
        store,
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        max_age_minutes=30,
        flood_max_age_minutes=90,
        summary_output=tmp_path / "summary.json",
        log_output=tmp_path / "runs.jsonl",
        now=now,
    )

    alert = manifest["datasets"]["rainfall_alerts"]
    assert manifest["health"]["state"] == "healthy"
    assert manifest["health"]["ready"] is True
    assert alert["row_count"] == 0
    assert alert["health"]["state"] == "healthy"
    assert alert["source"]["outcome"] == "empty"
    assert store.read_dataset(manifest, "rainfall_alerts") == []
    assert manifest["metadata"]["source_retries"]["flood_sensors"]["total"] == 2
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["metrics"]["source_retry_total"] == 2


def test_empty_observation_dataset_is_invalid_even_with_empty_source_outcome():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    _alerts, rain, _flood = live_scraper_records(now)
    records = {
        "rainfall_alerts": [],
        "rain_gauges": rain,
        "flood_sensors": [],
    }
    sources = {
        "rainfall_alerts": wra_api_source(
            "rainfall_alerts",
            [],
            now,
            outcome="empty",
        ),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source(
            "flood_sensors",
            [],
            now,
            outcome="empty",
        ),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )

    flood_payload = next(payload for payload in payloads if payload.name == "flood_sensors")
    assert flood_payload.health["state"] == "invalid"
    assert flood_payload.health["schema_errors"] == ["dataset contains no records"]


def test_missing_minxiong_observation_coverage_stays_not_ready_on_refresh():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    _alerts, rain, flood = live_scraper_records(now)
    for record in rain:
        record["行政區"] = "嘉義縣太保市"
    records = {
        "rainfall_alerts": [],
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        "rainfall_alerts": wra_api_source(
            "rainfall_alerts",
            [],
            now,
            outcome="empty",
        ),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source("flood_sensors", flood, now),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )
    feature_payload = next(payload for payload in payloads if payload.name == "minxiong_features")
    refreshed = refresh_dataset_health(feature_payload.health, mode="live", now=now)

    assert feature_payload.records[0]["data_ready"] == "false"
    assert feature_payload.records[0]["coverage_ready"] == "false"
    assert feature_payload.records[0]["coverage_gaps"] == "rain_gauges=0;flood_sensors=0"
    assert feature_payload.health["state"] == "coverage_missing"
    assert refreshed["state"] == "coverage_missing"
    assert refreshed["ready"] is False


def test_stale_official_alert_uses_observation_time_and_stays_stale_on_refresh():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)
    alert_observed_at = (now - timedelta(minutes=31)).isoformat(timespec="seconds")
    alerts = [
        {
            **alerts[0],
            "水情時間": "2026-07-11 09:29",
            "水情時間ISO": alert_observed_at,
            "警戒": "1級警戒",
            "警戒級別": "1",
        }
    ]
    records = {
        "rainfall_alerts": alerts,
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        "rainfall_alerts": wra_api_source(
            "rainfall_alerts",
            alerts,
            now,
            outcome="stale",
        ),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source("flood_sensors", flood, now),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )
    alert_payload = next(payload for payload in payloads if payload.name == "rainfall_alerts")
    refreshed = refresh_dataset_health(alert_payload.health, mode="live", now=now)

    assert alert_payload.health["observed_at"] == alert_observed_at
    assert alert_payload.health["state"] == "stale"
    assert refreshed["state"] == "stale"


def test_disabled_flood_sensor_cannot_make_dataset_fresh():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)
    active_observed_at = (now - timedelta(minutes=91)).isoformat(timespec="seconds")
    flood[0]["啟用狀態"] = "true"
    flood[0]["水情時間ISO"] = active_observed_at
    flood[1]["啟用狀態"] = "false"
    flood[1]["水情時間ISO"] = now.isoformat(timespec="seconds")
    records = {
        "rainfall_alerts": alerts,
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        "rainfall_alerts": wra_api_source("rainfall_alerts", alerts, now),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source(
            "flood_sensors",
            flood,
            now,
            outcome="stale",
        ),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        flood_max_age_minutes=90,
        now=now,
    )
    flood_payload = next(payload for payload in payloads if payload.name == "flood_sensors")
    refreshed = refresh_dataset_health(flood_payload.health, mode="live", now=now)

    assert flood_payload.health["observed_at"] == active_observed_at
    assert flood_payload.health["state"] == "stale"
    assert refreshed["state"] == "stale"


def test_all_disabled_flood_sensors_fall_back_to_record_timestamps():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)
    for record in flood:
        record["啟用狀態"] = "false"
    records = {
        "rainfall_alerts": alerts,
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        "rainfall_alerts": wra_api_source("rainfall_alerts", alerts, now),
        "rain_gauges": api_source(rain, now),
        "flood_sensors": wra_api_source("flood_sensors", flood, now),
    }

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        flood_max_age_minutes=90,
        now=now,
    )
    flood_payload = next(payload for payload in payloads if payload.name == "flood_sensors")

    assert flood_payload.health["state"] == "healthy"
    assert flood_payload.health["observed_at"] == now.isoformat(timespec="seconds")
    assert flood_payload.health["schema_errors"] == []


def test_alert_schema_drift_never_uses_scraper_fallback(monkeypatch):
    class DriftingAlertAdapter:
        dataset = "rainfall_alerts"

        def collect(self):
            raise SourceSchemaError("schema_drift", "WRA alert contract changed")

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: pytest.fail("schema drift must not use alert fallback"),
    )

    with pytest.raises(SourceSchemaError, match="WRA alert contract changed"):
        collector.collect_records(
            mode="live",
            county="10010",
            headed=False,
            timeout=1000,
            debug_dir=None,
            alert_source="auto",
            alert_adapter=DriftingAlertAdapter(),
        )


def test_live_collection_uses_api_rain_without_calling_rain_scraper(monkeypatch):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)

    class FakeAdapter:
        dataset = "rain_gauges"

        def collect(self):
            return SourceResult("rain_gauges", rain, api_source(rain, now))

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: alerts,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_flood_live",
        lambda **_kwargs: flood,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_rain_live",
        lambda **_kwargs: pytest.fail("rain scraper must not run after API success"),
    )

    collection = collector.collect_records(
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        rain_source="api",
        flood_source="scraper",
        rain_adapter=FakeAdapter(),
        now=now,
    )

    assert collection.records["rain_gauges"] == rain
    assert collection.sources["rain_gauges"].source_kind == "api"
    assert collection.sources["flood_sensors"].source_kind == "scraper_fallback"


def test_live_snapshot_persists_api_and_fallback_provenance(tmp_path, monkeypatch):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)

    class FakeAdapter:
        dataset = "rain_gauges"

        def collect(self):
            return SourceResult("rain_gauges", rain, api_source(rain, now))

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: alerts,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_flood_live",
        lambda **_kwargs: flood,
    )
    store = SnapshotStore(tmp_path / "operations")

    manifest = collector.run_collection(
        store,
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        max_age_minutes=30,
        summary_output=tmp_path / "summary.json",
        log_output=tmp_path / "runs.jsonl",
        now=now,
        rain_source="api",
        flood_source="scraper",
        rain_adapter=FakeAdapter(),
    )

    rain_details = manifest["datasets"]["rain_gauges"]
    flood_details = manifest["datasets"]["flood_sensors"]
    assert rain_details["source"]["source_kind"] == "api"
    assert rain_details["source"]["dataset_id"] == "O-A0002-001"
    assert rain_details["health"]["state"] == "healthy"
    assert flood_details["source"]["source_kind"] == "scraper_fallback"
    assert flood_details["health"]["state"] == "degraded"
    assert manifest["health"]["ready"] is False
    assert manifest["metadata"]["source_kinds"]["rain_gauges"] == "api"


def test_live_collection_falls_back_only_for_request_failures(monkeypatch):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)

    class FailingAdapter:
        dataset = "rain_gauges"

        def collect(self):
            raise SourceRequestError("transport", "CWA unavailable")

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: alerts,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_rain_live",
        lambda **_kwargs: rain,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_flood_live",
        lambda **_kwargs: flood,
    )

    collection = collector.collect_records(
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        rain_source="auto",
        flood_source="scraper",
        rain_adapter=FailingAdapter(),
        now=now,
    )

    source = collection.sources["rain_gauges"]
    assert source.source_kind == "scraper_fallback"
    assert source.outcome == "fallback"
    assert source.fallback_reason_kind == "transport"


def test_live_collection_rejects_schema_drift_without_fallback(monkeypatch):
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, _rain, _flood = live_scraper_records(now)

    class DriftingAdapter:
        dataset = "rain_gauges"

        def collect(self):
            raise SourceSchemaError("schema_drift", "contract changed")

    monkeypatch.setattr(
        collector.rainfall_alerts,
        "scrape_with_playwright",
        lambda **_kwargs: alerts,
    )
    monkeypatch.setattr(
        collector.hydrological_data,
        "scrape_rain_live",
        lambda **_kwargs: pytest.fail("schema drift must not use scraper fallback"),
    )

    with pytest.raises(SourceSchemaError, match="contract changed"):
        collector.collect_records(
            mode="live",
            county="10010",
            headed=False,
            timeout=1000,
            debug_dir=None,
            rain_source="auto",
            rain_adapter=DriftingAdapter(),
            now=now,
        )


def test_scraper_fallback_payload_is_degraded_and_not_ready():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    alerts, rain, flood = live_scraper_records(now)
    records = {
        "rainfall_alerts": alerts,
        "rain_gauges": rain,
        "flood_sensors": flood,
    }
    sources = {
        name: collector._scraper_source(
            name,
            dataset_records,
            source_url=f"https://example.test/{name}",
        )
        for name, dataset_records in records.items()
    }
    records["location_reference"] = collector.build_operational_locations(
        records,
        mode="live",
        now=now,
    )
    sources["location_reference"] = collector._derived_source(
        "location_reference",
        records["location_reference"],
        inputs={"rain_gauges": sources["rain_gauges"]},
        now=now,
    )

    payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )

    rain_payload = next(payload for payload in payloads if payload.name == "rain_gauges")
    assert rain_payload.health["state"] == "degraded"
    assert rain_payload.health["ready"] is False
    assert rain_payload.health["degradation_reasons"] == ["scraper_fallback"]

    records["rain_gauges"][0].pop("雨量站")
    invalid_payloads = collector.build_payloads(
        records,
        sources=sources,
        mode="live",
        max_age_minutes=30,
        now=now,
    )
    invalid_rain = next(
        payload for payload in invalid_payloads if payload.name == "rain_gauges"
    )
    assert invalid_rain.health["state"] == "invalid"
