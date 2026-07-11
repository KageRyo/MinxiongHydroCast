from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from floodcastminxiong.operations import collector
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


def test_live_payloads_use_official_product_classifications():
    now = datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ)
    records = collector.collect_records(
        mode="demo",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
    )
    records["location_reference"] = collector.build_operational_locations(
        records,
        mode="live",
        now=now,
    )

    payloads = collector.build_payloads(
        records,
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
