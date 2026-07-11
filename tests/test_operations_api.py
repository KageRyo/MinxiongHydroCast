import json
import threading
from datetime import datetime
from urllib.error import HTTPError
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from floodcastminxiong.operations.api import (
    build_server,
    metrics_payload,
    shadow_metrics_payload,
    shadow_payload,
    status_payload,
)
from floodcastminxiong.operations.collector import run_collection
from floodcastminxiong.operations.schemas import (
    DatasetResponse,
    ForecastResponse,
    HealthResponse,
    ShadowResponse,
    StatusResponse,
)
from floodcastminxiong.operations.snapshot_store import SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def create_demo_store(tmp_path) -> SnapshotStore:
    store = SnapshotStore(tmp_path / "operations")
    run_collection(
        store,
        mode="demo",
        county="10010",
        headed=False,
        timeout=1000,
        debug_dir=None,
        max_age_minutes=30,
        summary_output=tmp_path / "summary.json",
        log_output=tmp_path / "runs.jsonl",
        now=datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ),
    )
    return store


def request_json(base_url: str, path: str) -> dict[str, object]:
    with urlopen(f"{base_url}{path}", timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def test_metrics_payload_exposes_readiness_attempt_and_dataset_age():
    metrics = metrics_payload(
        StatusResponse(
            state="healthy",
            ready=True,
            checked_at="2026-07-11T10:00:00+08:00",
            latest_snapshot=None,
            latest_attempt={
                "snapshot_id": "snapshot-1",
                "status": "ok",
                "completed_at": "2026-07-11T10:00:00+08:00",
            },
            datasets={
                "rain_gauges": {
                    "product_type": "official_observation",
                    "path": "datasets/rain_gauges.csv",
                    "row_count": 1,
                    "fields": ["observed_at"],
                    "schema_sha256": "0" * 64,
                    "sha256": "1" * 64,
                    "health": {
                        "state": "healthy",
                        "ready": True,
                        "observed_at": "2026-07-11T09:55:30+08:00",
                        "age_minutes": 4.5,
                        "max_age_minutes": 30.0,
                        "schema_sha256": "0" * 64,
                        "schema_errors": [],
                    },
                }
            },
        )
    )

    assert "floodcastminxiong_ready 1" in metrics
    assert "floodcastminxiong_last_attempt_success 1" in metrics
    assert 'dataset="rain_gauges"} 4.5' in metrics
    assert 'dataset="rain_gauges",state="healthy"} 1' in metrics


def test_shadow_payload_defaults_to_blocked_and_exports_metrics(tmp_path):
    store = SnapshotStore(tmp_path / "operations")

    report = shadow_payload(store)
    metrics = shadow_metrics_payload(report)

    assert report.state == "not_evaluated"
    assert report.shadow_gate_passed is False
    assert report.notification_allowed is False
    assert "floodcastminxiong_shadow_gate_passed 0" in metrics
    assert "floodcastminxiong_notification_allowed 0" in metrics


def test_status_reports_collector_error_without_hiding_last_snapshot(tmp_path):
    store = create_demo_store(tmp_path)
    latest_snapshot_id = store.read_latest()["snapshot_id"]
    failed_at = datetime(2026, 7, 11, 10, 10, tzinfo=TAIPEI_TZ)
    store.publish_failure(
        mode="live",
        started_at=failed_at.isoformat(),
        completed_at=failed_at.isoformat(),
        failure_reason="source unavailable",
        now=failed_at,
    )

    status = status_payload(store, now=failed_at)

    assert status.state == "collector_error"
    assert status.ready is False
    assert status.latest_snapshot.snapshot_id == latest_snapshot_id
    assert status.latest_attempt.failure_reason == "source unavailable"


def test_status_reports_corrupt_pointer_as_storage_error(tmp_path):
    store = SnapshotStore(tmp_path / "operations")
    store.initialize()
    store.latest_path.write_text("{not-json", encoding="utf-8")

    status = status_payload(
        store,
        now=datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ),
    )

    assert status.state == "storage_error"
    assert status.ready is False
    assert "invalid snapshot pointer" in status.failure_reason


def test_status_reports_tampered_dataset_as_storage_error(tmp_path):
    store = create_demo_store(tmp_path)
    latest = store.read_latest()
    details = latest["datasets"]["rain_gauges"]
    path = store.snapshots_dir / latest["snapshot_id"] / details["path"]
    path.write_text("corrupt\n", encoding="utf-8")

    status = status_payload(
        store,
        now=datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ),
    )

    assert status.state == "storage_error"
    assert status.ready is False
    assert "dataset checksum mismatch" in status.failure_reason


def test_status_reports_invalid_response_contract_as_storage_error():
    class InvalidStatusStore:
        def read_latest(self):
            return {
                "snapshot_id": "snapshot-1",
                "mode": "unexpected",
                "completed_at": "2026-07-11T10:00:00+08:00",
                "datasets": {},
            }

        def read_latest_attempt(self):
            return None

        def verify_snapshot(self, _manifest):
            return []

    status = status_payload(
        InvalidStatusStore(),
        now=datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ),
    )

    assert status.state == "storage_error"
    assert status.ready is False
    assert "invalid snapshot response contract" in status.failure_reason


def test_dataset_response_rejects_row_count_mismatch():
    with pytest.raises(ValidationError, match="row_count must match"):
        DatasetResponse(
            snapshot_id="snapshot-1",
            generated_at="2026-07-11T10:00:00+08:00",
            mode="live",
            dataset="rain_gauges",
            product_type="official_observation",
            notice="Validated observation.",
            health={
                "state": "healthy",
                "ready": True,
                "observed_at": "2026-07-11T10:00:00+08:00",
                "age_minutes": 0.0,
                "max_age_minutes": 30.0,
                "schema_sha256": "0" * 64,
                "schema_errors": [],
            },
            row_count=2,
            records=[{"station": "Minxiong"}],
        )


def test_api_serves_status_classified_data_and_operator_view(tmp_path):
    server = build_server(create_demo_store(tmp_path), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        health = HealthResponse.model_validate(request_json(base_url, "/healthz"))
        assert health.status == "ok"
        status = StatusResponse.model_validate(request_json(base_url, "/api/v1/status"))
        assert status.state == "demo"
        assert status.ready is False

        alerts = DatasetResponse.model_validate(
            request_json(base_url, "/api/v1/official-alerts/rainfall")
        )
        assert alerts.product_type == "demo_fixture"
        assert alerts.row_count == 2
        assert "Not live or official data" in alerts.notice

        observations = DatasetResponse.model_validate(
            request_json(base_url, "/api/v1/observations/rain-gauges")
        )
        assert observations.product_type == "demo_fixture"
        assert observations.row_count == 2
        assert observations.source.source_kind == "demo_fixture"
        assert observations.source.dataset_id == "demo-rain_gauges"

        features = DatasetResponse.model_validate(
            request_json(base_url, "/api/v1/features/minxiong")
        )
        assert features.product_type == "demo_fixture"
        assert features.records[0]["township"] == "民雄鄉"
        assert features.records[0]["qpe_available"] == "false"

        locations = DatasetResponse.model_validate(request_json(base_url, "/api/v1/locations"))
        assert locations.product_type == "demo_fixture"
        assert locations.row_count == 4

        forecast = ForecastResponse.model_validate(
            request_json(base_url, "/api/v1/experimental-forecasts")
        )
        assert forecast.available is False
        assert forecast.product_type == "experimental_forecast"

        shadow = ShadowResponse.model_validate(
            request_json(base_url, "/api/v1/shadow-readiness")
        )
        assert shadow.state == "not_evaluated"
        assert shadow.notification_allowed is False

        with urlopen(f"{base_url}/metrics", timeout=3) as response:
            metrics = response.read().decode("utf-8")
        assert "floodcastminxiong_ready 0" in metrics
        assert "floodcastminxiong_last_attempt_success 1" in metrics
        assert "floodcastminxiong_shadow_gate_passed 0" in metrics
        assert 'dataset="rain_gauges",state="demo"' in metrics
        assert 'dataset="rain_gauges",source_kind="demo_fixture"' in metrics

        with urlopen(f"{base_url}/", timeout=3) as response:
            page = response.read().decode("utf-8")
        assert "FloodCastMinxiong Operations" in page
        assert "Source classification:" in page
        assert "Not an official warning" in page
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def test_ready_endpoint_returns_503_for_demo_data(tmp_path):
    server = build_server(create_demo_store(tmp_path), host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with pytest.raises(HTTPError) as exc_info:
            urlopen(f"http://127.0.0.1:{server.server_port}/readyz", timeout=3)
        assert exc_info.value.code == 503
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
