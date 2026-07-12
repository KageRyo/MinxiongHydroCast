import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from floodcastminxiong.ingestion.http_client import ReliableJsonClient, RetryPolicy
from floodcastminxiong.ingestion.source_adapter import SourceRequestError, SourceSchemaError
from floodcastminxiong.ingestion.wra_rainfall_alert_api import (
    DEFAULT_ENDPOINT,
    WraRainfallAlertAdapter,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
FIXTURE = Path("tests/fixtures/wra_rainfall_warning.json")


class FakeResponse:
    def __init__(
        self,
        content: bytes,
        *,
        status_code: int = 200,
        url: str = f"{DEFAULT_ENDPOINT}?%24top=1000&%24skip=0",
    ) -> None:
        self.content = content
        self.status_code = status_code
        self.url = url

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def client_for(
    payload: dict[str, object],
    *,
    requests_seen: list[dict[str, object]] | None = None,
) -> ReliableJsonClient:
    content = json.dumps(payload, ensure_ascii=False).encode()

    def fake_get(_url: str, **kwargs: object) -> FakeResponse:
        if requests_seen is not None:
            requests_seen.append(kwargs)
        return FakeResponse(content)

    return ReliableJsonClient(http_get=fake_get, minimum_interval_seconds=0)


def test_wra_adapter_validates_fixture_filters_county_and_normalizes_records():
    requests_seen: list[dict[str, object]] = []
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(fixture_payload(), requests_seen=requests_seen),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    result = adapter.collect()

    assert result.dataset == "rainfall_alerts"
    assert len(result.records) == 1
    assert result.records[0] == {
        "雨量站代碼": "C0M760",
        "縣市代碼": "10010",
        "鄉鎮代碼": "10010050",
        "地區": "民雄鄉雙福村、福樂村",
        "水情時間": "2026-07-12T03:20:00",
        "水情時間ISO": "2026-07-12T03:20:00+08:00",
        "警戒": "1級警戒",
        "警戒級別": "1",
        "影響村落": "民雄鄉雙福村、福樂村",
        "10分鐘雨量mm": "4.5",
        "1小時雨量mm": "18",
        "3小時雨量mm": "55.5",
        "6小時雨量mm": "82",
        "12小時雨量mm": "105",
        "24小時雨量mm": "130.5",
        "抓取時間": "2026-07-12T03:25:00+08:00",
        "資料模式": "live",
        "資料來源": f"{DEFAULT_ENDPOINT}?%24top=1000&%24skip=0",
    }
    assert requests_seen == [
        {
            "params": {"$top": "1000", "$skip": "0"},
            "headers": {"apikey": "real-secret"},
            "timeout": 30,
        }
    ]
    assert "real-secret" not in result.provenance.source_url
    assert result.provenance.source_kind == "api"
    assert result.provenance.outcome == "ok"
    assert result.provenance.dataset_id == "WRA-Rainfall-Warning-v2"
    assert len(result.provenance.content_sha256) == 64


def test_wra_adapter_accepts_documented_empty_response_as_successful_empty():
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for({"UpdataTime": None, "Data": []}),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    result = adapter.collect()

    assert result.records == []
    assert result.provenance.outcome == "empty"
    assert result.provenance.source_kind == "api"


def test_wra_adapter_uses_opaque_codes_when_affected_area_is_blank():
    payload = fixture_payload()
    payload["Data"][0]["AffectedArea"] = ""
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    record = adapter.collect().records[0]

    assert record["地區"] == "10010/10010050"
    assert record["縣市代碼"] == "10010"
    assert record["鄉鎮代碼"] == "10010050"


def test_wra_adapter_marks_old_observations_stale():
    now = datetime(2026, 7, 12, 3, 20, tzinfo=TAIPEI_TZ) + timedelta(minutes=31)
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(fixture_payload()),
        now=now,
    )

    assert adapter.collect().provenance.outcome == "stale"


@pytest.mark.parametrize(
    ("mutate", "expected_message"),
    [
        (lambda row: row.update({"Unexpected": "drift"}), "Extra inputs"),
        (lambda row: row.pop("H24"), "Field required"),
        (lambda row: row.update({"H1": "18.0"}), "valid number"),
        (lambda row: row.update({"WarningLevel": 3}), "less than or equal to 2"),
    ],
)
def test_wra_adapter_rejects_schema_drift(mutate, expected_message):
    payload = fixture_payload()
    mutate(payload["Data"][0])
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"
    assert expected_message.lower() in str(exc_info.value).lower()


def test_wra_adapter_rejects_observation_timestamp_with_offset():
    payload = fixture_payload()
    payload["Data"][0]["Time"] = "2026-07-12T03:20:00+08:00"
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"


def test_wra_adapter_rejects_invalid_timestamp_outside_target_county():
    payload = fixture_payload()
    payload["Data"][1]["Time"] = "not-a-time"
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"


def test_wra_adapter_rejects_whitespace_only_opaque_codes():
    payload = fixture_payload()
    payload["Data"][1]["CityCode"] = "   "
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client_for(payload),
        now=datetime(2026, 7, 12, 3, 25, tzinfo=TAIPEI_TZ),
    )

    with pytest.raises(SourceSchemaError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "schema_drift"


def test_wra_adapter_requires_key_before_request():
    adapter = WraRainfallAlertAdapter(
        api_key="",
        county_code="10010",
        client=client_for(fixture_payload()),
    )

    with pytest.raises(SourceRequestError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "authentication"


def test_wra_adapter_preserves_typed_transport_failure():
    def failed_get(_url: str, **_kwargs: object) -> FakeResponse:
        raise OSError("network down")

    client = ReliableJsonClient(
        http_get=failed_get,
        retry_policy=RetryPolicy(attempts=1),
        minimum_interval_seconds=0,
    )
    adapter = WraRainfallAlertAdapter(
        api_key="real-secret",
        county_code="10010",
        client=client,
    )

    with pytest.raises(SourceRequestError) as exc_info:
        adapter.collect()

    assert exc_info.value.kind == "transport"
    assert "real-secret" not in str(exc_info.value)
