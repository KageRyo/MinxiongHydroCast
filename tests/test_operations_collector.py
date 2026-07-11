from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from floodcastminxiong.operations import collector
from floodcastminxiong.ingestion.source_adapter import (
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceSchemaError,
    records_sha256,
)
from floodcastminxiong.operations.snapshot_store import SnapshotStore

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
        raise SourceSchemaError("schema_drift", "CWA contract changed")

    monkeypatch.setattr(collector, "collect_records", fail_collection)
    with pytest.raises(SourceSchemaError, match="contract changed"):
        run_demo(store, tmp_path, now)

    attempt = store.read_latest_attempt()
    assert attempt["status"] == "error"
    assert attempt["metadata"]["failure_kind"] == "schema_drift"


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
        "scrape_live",
        lambda **_kwargs: pytest.fail("rain scraper must not run after API success"),
    )

    collection = collector.collect_records(
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        rain_source="api",
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
        "scrape_live",
        lambda **_kwargs: (rain, flood),
    )

    collection = collector.collect_records(
        mode="live",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        rain_source="auto",
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
        "scrape_live",
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
