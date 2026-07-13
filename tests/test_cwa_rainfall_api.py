import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.ingestion.cwa_rainfall_api import CwaRainGaugeAdapter
from minxionghydrocast.ingestion.http_client import ReliableJsonClient
from minxionghydrocast.ingestion.source_adapter import (
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceSchemaError,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
FIXTURE = Path("tests/fixtures/cwa_o_a0002_001.json")


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.status_code = 200
        self.url = (
            "https://opendata.cwa.gov.tw/api/v1/rest/datastore/O-A0002-001"
            "?Authorization=real-secret&format=JSON"
        )

    def raise_for_status(self) -> None:
        return None


def client_for(payload: dict[str, object]) -> ReliableJsonClient:
    content = json.dumps(payload, ensure_ascii=False).encode()
    return ReliableJsonClient(
        http_get=lambda _url, **_kwargs: FakeResponse(content),
        minimum_interval_seconds=0,
    )


def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_cwa_adapter_validates_official_fixture_and_normalizes_chiayi_records():
    now = datetime(2026, 7, 11, 23, 25, tzinfo=TAIPEI_TZ)
    adapter = CwaRainGaugeAdapter(
        authorization="real-secret",
        county_code="10010",
        client=client_for(fixture_payload()),
        now=now,
    )

    result = adapter.collect()

    assert result.dataset == "rain_gauges"
    assert len(result.records) == 1
    assert result.records[0]["雨量站"] == "民雄"
    assert result.records[0]["雨量站代碼"] == "C0M760"
    assert result.records[0]["行政區"] == "嘉義縣民雄鄉"
    assert result.records[0]["1小時累積雨量mm"] == "3.5"
    assert result.records[0]["24小時累積雨量mm"] == "49"
    assert result.records[0]["緯度"] == "23.551742"
    assert result.records[0]["經度"] == "120.428444"
    assert "real-secret" not in result.records[0]["資料來源"]
    assert result.provenance.source_kind == "api"
    assert result.provenance.outcome == "ok"
    assert result.provenance.dataset_id == "O-A0002-001"
    assert len(result.provenance.content_sha256) == 64


def test_cwa_adapter_marks_old_observations_stale():
    now = datetime(2026, 7, 11, 23, 20, tzinfo=TAIPEI_TZ) + timedelta(minutes=31)
    adapter = CwaRainGaugeAdapter(
        authorization="real-secret",
        county_code="10010",
        client=client_for(fixture_payload()),
        now=now,
    )

    assert adapter.collect().provenance.outcome == "stale"


def test_cwa_adapter_rejects_schema_drift_without_fallback():
    payload = fixture_payload()
    payload["records"]["Station"][0]["UnexpectedField"] = "drift"
    adapter = CwaRainGaugeAdapter(
        authorization="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 11, 23, 25, tzinfo=TAIPEI_TZ),
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"


def test_cwa_adapter_requires_key_before_request():
    adapter = CwaRainGaugeAdapter(
        authorization="",
        county_code="10010",
        client=client_for(fixture_payload()),
    )

    with pytest.raises(SourceRequestError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "authentication"


def test_source_result_represents_expected_empty_api_response_explicitly():
    provenance = SourceProvenance(
        source_kind="api",
        outcome="empty",
        authority="Water Resources Agency, Taiwan",
        dataset_id="rainfall-alerts",
        source_url="https://example.test/alerts",
        fetched_at="2026-07-11T23:20:00+08:00",
        schema_version="alerts-v1",
        content_sha256="0" * 64,
    )

    result = SourceResult("rainfall_alerts", [], provenance)

    assert result.records == []
    assert result.provenance.outcome == "empty"
