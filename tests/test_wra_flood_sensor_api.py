import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pytest

from minxionghydrocast.ingestion.http_client import ReliableJsonClient
from minxionghydrocast.ingestion.hydrological_data import FLOOD_FIELDNAMES
from minxionghydrocast.ingestion.source_adapter import SourceSchemaError
from minxionghydrocast.ingestion.wra_flood_sensor_api import (
    CATALOG_DATASET_ID,
    LATEST_DATASET_ID,
    WraFloodSensorAdapter,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
LATEST_FIXTURE = Path("tests/fixtures/wra_iow_latest.json")
CATALOG_FIXTURE = Path("tests/fixtures/wra_iow_catalog.json")


class FakeResponse:
    def __init__(self, content: bytes, url: str):
        self.content = content
        self.status_code = 200
        self.url = url

    def raise_for_status(self) -> None:
        return None


class PaginatedGet:
    def __init__(
        self,
        latest: list[dict[str, str]],
        catalog: list[dict[str, str]],
    ) -> None:
        self.payloads = {
            LATEST_DATASET_ID: latest,
            CATALOG_DATASET_ID: catalog,
        }
        self.calls: list[tuple[str, int, int]] = []
        self.response_contents: list[bytes] = []

    def __call__(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ) -> FakeResponse:
        del headers, timeout
        dataset_id = url.rsplit("/", maxsplit=1)[-1]
        page = int(params["page"])
        size = int(params["size"])
        start = (page - 1) * size
        page_payload = self.payloads[dataset_id][start : start + size]
        content = json.dumps(page_payload, ensure_ascii=False).encode("utf-8")
        self.calls.append((dataset_id, page, size))
        self.response_contents.append(content)
        return FakeResponse(content, f"{url}?{urlencode(params)}")


def fixture_payloads() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    return (
        json.loads(LATEST_FIXTURE.read_text(encoding="utf-8")),
        json.loads(CATALOG_FIXTURE.read_text(encoding="utf-8")),
    )


def adapter_for(
    latest: list[dict[str, str]],
    catalog: list[dict[str, str]],
    **kwargs: Any,
) -> tuple[WraFloodSensorAdapter, PaginatedGet]:
    http_get = PaginatedGet(latest, catalog)
    client = ReliableJsonClient(
        http_get=http_get,
        minimum_interval_seconds=0,
    )
    options: dict[str, Any] = {
        "county_code": "10010",
        "town_code": "10010050",
        "client": client,
        "now": datetime(2026, 7, 12, 12, 15, tzinfo=TAIPEI_TZ),
    }
    options.update(kwargs)
    return WraFloodSensorAdapter(**options), http_get


def test_adapter_joins_official_feeds_and_emits_operational_flood_schema():
    latest, catalog = fixture_payloads()
    adapter, http_get = adapter_for(latest, catalog)

    result = adapter.collect()

    assert result.dataset == "flood_sensors"
    assert len(result.records) == 1
    record = result.records[0]
    assert set(record) == set(FLOOD_FIELDNAMES)
    assert record["感測器代碼"] == "00707a34-700c-4e01-b091-396378c234f6"
    assert record["觀測站代碼"] == "3765000FLCYC136"
    assert record["縣市代碼"] == "10010"
    assert record["鄉鎮代碼"] == "10010050"
    assert record["縣市"] == "嘉義縣"
    assert record["鄉鎮"] == "民雄鄉"
    assert record["感測器名稱"] == "CYC136 民雄鄉大崎村淹水深度"
    assert record["觀測站名稱"] == "CYC136 民雄鄉大崎村"
    assert record["維運單位"] == "嘉義縣政府水利處"
    assert record["類別"] == "淹水深度"
    assert record["地址"] == ""
    assert record["緯度"] == "23.517036"
    assert record["經度"] == "120.473759"
    assert record["啟用狀態"] == "true"
    assert record["水情時間ISO"] == "2026-07-12T11:45:35+08:00"
    assert record["目前感測值"] == "12.50 cm"
    assert record["目前感測值數值"] == "12.5"
    assert record["目前感測值單位"] == "cm"
    assert record["資料產出時間"] == record["水情時間"]
    assert record["資料產出時間ISO"] == record["水情時間ISO"]
    assert record["資料模式"] == "live"
    assert LATEST_DATASET_ID in record["資料來源"]
    assert result.provenance.source_kind == "api"
    assert result.provenance.outcome == "ok"
    assert result.provenance.dataset_id == f"{LATEST_DATASET_ID}+{CATALOG_DATASET_ID}"
    expected_hash = hashlib.sha256(b"".join(http_get.response_contents)).hexdigest()
    assert result.provenance.content_sha256 == expected_hash


def test_adapter_filters_by_county_when_town_is_not_configured():
    latest, catalog = fixture_payloads()
    adapter, _http_get = adapter_for(latest, catalog, town_code=None)

    result = adapter.collect()

    assert len(result.records) == 2
    assert {record["鄉鎮代碼"] for record in result.records} == {"10010030", "10010050"}


def test_adapter_paginates_both_feeds_until_a_short_page():
    latest, catalog = fixture_payloads()
    adapter, http_get = adapter_for(latest, catalog, page_size=1)

    result = adapter.collect()

    assert len(result.records) == 1
    for dataset_id in (LATEST_DATASET_ID, CATALOG_DATASET_ID):
        assert [
            page for called_dataset, page, _size in http_get.calls if called_dataset == dataset_id
        ] == [1, 2, 3]


def test_adapter_rejects_repeated_full_page_instead_of_looping_forever():
    latest, catalog = fixture_payloads()

    def repeating_get(
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str] | None,
        timeout: float,
    ) -> FakeResponse:
        del headers, timeout
        dataset_id = url.rsplit("/", maxsplit=1)[-1]
        payload = latest if dataset_id == LATEST_DATASET_ID else catalog
        content = json.dumps(payload[:1], ensure_ascii=False).encode("utf-8")
        return FakeResponse(content, f"{url}?{urlencode(params)}")

    adapter = WraFloodSensorAdapter(
        county_code="10010",
        page_size=1,
        client=ReliableJsonClient(http_get=repeating_get, minimum_interval_seconds=0),
    )

    with pytest.raises(SourceSchemaError, match="repeated a full page"):
        adapter.collect()


def test_adapter_marks_target_feed_stale_after_default_ninety_minutes():
    latest, catalog = fixture_payloads()
    adapter, _http_get = adapter_for(
        latest,
        catalog,
        now=datetime(2026, 7, 12, 13, 16, tzinfo=TAIPEI_TZ),
    )

    assert adapter.collect().provenance.outcome == "stale"


@pytest.mark.parametrize("feed", ["latest", "catalog"])
def test_adapter_hard_fails_on_extra_upstream_fields(feed: str):
    latest, catalog = fixture_payloads()
    payload = latest if feed == "latest" else catalog
    payload[0]["unexpected"] = "schema drift"
    adapter, _http_get = adapter_for(latest, catalog)

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"


def test_adapter_hard_fails_when_target_measurement_has_no_metadata():
    latest, catalog = fixture_payloads()
    catalog = [
        record for record in catalog if record["sensorid"] != "00707a34-700c-4e01-b091-396378c234f6"
    ]
    adapter, _http_get = adapter_for(latest, catalog)

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"
    assert "missing metadata" in str(exc_info.value)


def test_adapter_rejects_empty_required_target_feed():
    latest, catalog = fixture_payloads()
    adapter, _http_get = adapter_for(
        latest,
        catalog,
        town_code="10010060",
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "empty_unexpected"


def test_adapter_requires_an_enabled_sensor_for_target_freshness():
    latest, catalog = fixture_payloads()
    target_id = "00707a34-700c-4e01-b091-396378c234f6"
    next(record for record in catalog if record["sensorid"] == target_id)["isenable"] = "false"
    adapter, _http_get = adapter_for(latest, catalog)

    with pytest.raises(SourceSchemaError, match="no enabled flood-depth sensors") as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "empty_unexpected"


def test_adapter_rejects_location_code_disagreement_after_join():
    latest, catalog = fixture_payloads()
    catalog[0]["areacode"] = "10010030"
    adapter, _http_get = adapter_for(latest, catalog)

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"
    assert "location codes disagree" in str(exc_info.value)


def test_adapter_rejects_negative_target_flood_depth():
    latest, catalog = fixture_payloads()
    target_id = "00707a34-700c-4e01-b091-396378c234f6"
    next(record for record in latest if record["sensorid"] == target_id)["latestvalue"] = "-1"
    adapter, _http_get = adapter_for(latest, catalog)

    with pytest.raises(SourceSchemaError, match="flood depth is negative") as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"
