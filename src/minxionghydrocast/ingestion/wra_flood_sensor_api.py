"""WRA Open Data IoW flood-depth sensor adapter."""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import unescape
from typing import Any, Callable, Literal, TypeVar
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion.http_client import ReliableJsonClient
from minxionghydrocast.ingestion.source_adapter import (
    SourceAdapterError,
    SourceProvenance,
    SourceResult,
    SourceSchemaError,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DATASET_NAME = "flood_sensors"
LATEST_DATASET_ID = "1b991bbb-ad85-4e7a-b931-06ce8749d3ed"
CATALOG_DATASET_ID = "21c50be1-7c4a-4fdf-a386-790625e984e7"
DEFAULT_BASE_URL = "https://opendata.wra.gov.tw/api/v2"
SCHEMA_VERSION = "wra-iow-flood-depth-v1"
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-"
    r"[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
LOGGER = logging.getLogger(__name__)


class WraIowSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


def _validate_sensor_id(value: str) -> str:
    if not UUID_PATTERN.fullmatch(value):
        raise ValueError("sensorid must be a canonical UUID")
    try:
        UUID(value)
    except ValueError as exc:
        raise ValueError("sensorid must be a valid UUID") from exc
    return value


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(TAIPEI_TZ)


def _parse_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("latestvalue must be numeric") from exc
    if not parsed.is_finite():
        raise ValueError("latestvalue must be finite")
    return parsed


def _numeric_text(value: str) -> str:
    return format(_parse_decimal(value).normalize(), "f")


class WraIowLatestMeasurement(WraIowSchema):
    sensor_id: str = Field(alias="sensorid")
    latest_value: str = Field(alias="latestvalue")
    timestamp: str
    area_code: str = Field(alias="areacode", pattern=r"^\d{8}$")
    county_code: str = Field(alias="countycode", pattern=r"^\d{5}$")

    @field_validator("sensor_id")
    @classmethod
    def sensor_id_is_uuid(cls, value: str) -> str:
        return _validate_sensor_id(value)

    @field_validator("latest_value")
    @classmethod
    def latest_value_is_numeric(cls, value: str) -> str:
        _parse_decimal(value)
        return value

    @field_validator("timestamp")
    @classmethod
    def timestamp_is_aware_iso8601(cls, value: str) -> str:
        _parse_timestamp(value, field_name="timestamp")
        return value


class WraIowSensorMetadata(WraIowSchema):
    category: Literal["淹水深度"]
    organization_name: str = Field(alias="orgname", min_length=1)
    sensor_id: str = Field(alias="sensorid")
    sensor_name: str = Field(alias="sensorname", min_length=1)
    sensor_full_name: str = Field(alias="sensorfullname", min_length=1)
    sensor_description: str = Field(alias="sensordescription", min_length=1)
    unit: Literal["cm"]
    observatory_identifier: str = Field(alias="observatoryidentifier", min_length=1)
    observatory_name: str = Field(alias="observatoryname", min_length=1)
    longitude: str
    latitude: str
    county_code: str = Field(alias="countycode", pattern=r"^\d{5}$")
    county_name: str = Field(alias="countyname", min_length=1)
    area_code: str = Field(alias="areacode", pattern=r"^\d{8}$")
    town_name: str = Field(alias="townname", min_length=1)
    is_enabled: Literal["true", "false"] = Field(alias="isenable")
    created_at: str = Field(alias="createdate")
    modified_at: str = Field(alias="modifydate")

    @field_validator("sensor_id")
    @classmethod
    def sensor_id_is_uuid(cls, value: str) -> str:
        return _validate_sensor_id(value)

    @field_validator("longitude")
    @classmethod
    def longitude_is_in_taiwan(cls, value: str) -> str:
        try:
            longitude = float(value)
        except ValueError as exc:
            raise ValueError("longitude must be numeric") from exc
        if not 118 <= longitude <= 123:
            raise ValueError("longitude is outside Taiwan bounds")
        return value

    @field_validator("latitude")
    @classmethod
    def latitude_is_in_taiwan(cls, value: str) -> str:
        try:
            latitude = float(value)
        except ValueError as exc:
            raise ValueError("latitude must be numeric") from exc
        if not 20 <= latitude <= 27:
            raise ValueError("latitude is outside Taiwan bounds")
        return value

    @field_validator("created_at", "modified_at")
    @classmethod
    def metadata_timestamp_is_aware_iso8601(cls, value: str) -> str:
        _parse_timestamp(value, field_name="metadata timestamp")
        return value


LATEST_LIST_ADAPTER = TypeAdapter(list[WraIowLatestMeasurement])
CATALOG_LIST_ADAPTER = TypeAdapter(list[WraIowSensorMetadata])
RecordT = TypeVar("RecordT", WraIowLatestMeasurement, WraIowSensorMetadata)


def _validated_records(
    raw_records: list[Any],
    *,
    adapter: TypeAdapter[list[RecordT]],
    dataset_id: str,
) -> list[RecordT]:
    try:
        return adapter.validate_python(raw_records, strict=True)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        location = ".".join(str(part) for part in first_error["loc"])
        raise SourceSchemaError(
            "schema_drift",
            f"WRA IoW {dataset_id} response contract changed at {location}: {first_error['msg']}",
        ) from exc


def _unique_by_sensor_id(
    records: list[RecordT],
    *,
    dataset_id: str,
) -> dict[str, RecordT]:
    indexed: dict[str, RecordT] = {}
    for record in records:
        if record.sensor_id in indexed:
            raise SourceSchemaError(
                "schema_drift",
                f"WRA IoW {dataset_id} returned duplicate sensorid {record.sensor_id}",
            )
        indexed[record.sensor_id] = record
    return indexed


class WraFloodSensorAdapter:
    """Join official IoW measurements with sensor metadata for one target region."""

    dataset = DATASET_NAME

    def __init__(
        self,
        *,
        county_code: str,
        town_code: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30,
        max_age_minutes: float = 90,
        page_size: int = 1000,
        page_retry_attempts: int = 3,
        page_retry_backoff_seconds: float = 0.5,
        client: ReliableJsonClient | None = None,
        now: datetime | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not re.fullmatch(r"\d{5}", county_code):
            raise ValueError("county_code must contain five digits")
        if town_code is not None and not re.fullmatch(r"\d{8}", town_code):
            raise ValueError("town_code must contain eight digits")
        if town_code is not None and not town_code.startswith(county_code):
            raise ValueError("town_code must belong to county_code")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_age_minutes <= 0:
            raise ValueError("max_age_minutes must be positive")
        if page_size < 1 or page_size > 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if page_retry_attempts < 1:
            raise ValueError("page_retry_attempts must be at least one")
        if page_retry_backoff_seconds < 0:
            raise ValueError("page_retry_backoff_seconds must not be negative")
        self.county_code = county_code
        self.town_code = town_code
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_age_minutes = max_age_minutes
        self.page_size = page_size
        self.page_retry_attempts = page_retry_attempts
        self.page_retry_backoff_seconds = page_retry_backoff_seconds
        self.client = client or ReliableJsonClient()
        self.now = now
        self._sleep = sleep

    @property
    def latest_endpoint(self) -> str:
        return f"{self.base_url}/{LATEST_DATASET_ID}"

    @property
    def catalog_endpoint(self) -> str:
        return f"{self.base_url}/{CATALOG_DATASET_ID}"

    def _params(self, page: int) -> dict[str, str]:
        return {
            "format": "JSON",
            "sort": "_importdate asc",
            "page": str(page),
            "size": str(self.page_size),
        }

    def _fetch_pages(self, endpoint: str) -> tuple[list[Any], list[bytes], str]:
        records: list[Any] = []
        contents: list[bytes] = []
        page_hashes: set[str] = set()
        source_url = endpoint
        page = 1
        while True:
            params = self._params(page)
            request_url = f"{endpoint}?{urlencode(params)}"
            for attempt in range(1, self.page_retry_attempts + 1):
                response = self.client.get_json(
                    endpoint,
                    params=params,
                    timeout_seconds=self.timeout_seconds,
                    redacted_url=request_url,
                    expected_root="array",
                )
                page_records = response.payload
                if not isinstance(page_records, list):
                    raise SourceSchemaError(
                        "schema_drift",
                        f"WRA IoW endpoint returned a non-array page: {endpoint}",
                    )
                if len(page_records) > self.page_size:
                    raise SourceSchemaError(
                        "schema_drift",
                        f"WRA IoW endpoint exceeded requested page size: {endpoint}",
                    )
                page_hash = hashlib.sha256(response.content).hexdigest()
                if not page_records or page_hash not in page_hashes:
                    break
                if attempt == self.page_retry_attempts:
                    raise SourceSchemaError(
                        "schema_drift",
                        "WRA IoW endpoint repeated a full page after "
                        f"{attempt} attempts: {endpoint}",
                    )
                delay = self.page_retry_backoff_seconds * (2 ** (attempt - 1))
                LOGGER.warning(
                    "wra_pagination_retry reason=repeated_full_page page=%d attempt=%d "
                    "attempts=%d backoff_seconds=%.3f url=%s",
                    page,
                    attempt,
                    self.page_retry_attempts,
                    delay,
                    request_url,
                )
                self._sleep(delay)
            page_hashes.add(page_hash)
            if page == 1:
                source_url = response.url
            records.extend(page_records)
            contents.append(response.content)
            if len(page_records) < self.page_size:
                return records, contents, source_url
            page += 1

    def _matches_target(self, measurement: WraIowLatestMeasurement) -> bool:
        if measurement.county_code != self.county_code:
            return False
        return self.town_code is None or measurement.area_code == self.town_code

    def collect(self) -> SourceResult:
        now = self.now or datetime.now(TAIPEI_TZ)
        if now.tzinfo is None:
            raise ValueError("now must include a timezone")
        now = now.astimezone(TAIPEI_TZ)
        fetched_at = now.isoformat(timespec="seconds")

        raw_measurements, latest_contents, source_url = self._fetch_pages(self.latest_endpoint)
        raw_catalog, catalog_contents, _ = self._fetch_pages(self.catalog_endpoint)
        measurements = _validated_records(
            raw_measurements,
            adapter=LATEST_LIST_ADAPTER,
            dataset_id=LATEST_DATASET_ID,
        )
        catalog = _validated_records(
            raw_catalog,
            adapter=CATALOG_LIST_ADAPTER,
            dataset_id=CATALOG_DATASET_ID,
        )
        _unique_by_sensor_id(measurements, dataset_id=LATEST_DATASET_ID)
        metadata_by_id = _unique_by_sensor_id(catalog, dataset_id=CATALOG_DATASET_ID)

        target_measurements = [
            measurement for measurement in measurements if self._matches_target(measurement)
        ]
        if not target_measurements:
            target = self.town_code or self.county_code
            raise SourceSchemaError(
                "empty_unexpected",
                f"WRA IoW returned no flood-depth measurements for target {target}",
            )

        joined: list[tuple[WraIowLatestMeasurement, WraIowSensorMetadata]] = []
        for measurement in target_measurements:
            if _parse_decimal(measurement.latest_value) < 0:
                raise SourceSchemaError(
                    "schema_drift",
                    f"WRA IoW flood depth is negative for sensorid {measurement.sensor_id}",
                )
            metadata = metadata_by_id.get(measurement.sensor_id)
            if metadata is None:
                raise SourceSchemaError(
                    "schema_drift",
                    f"WRA IoW measurement sensorid {measurement.sensor_id} is missing metadata",
                )
            if (
                measurement.county_code != metadata.county_code
                or measurement.area_code != metadata.area_code
            ):
                raise SourceSchemaError(
                    "schema_drift",
                    f"WRA IoW location codes disagree for sensorid {measurement.sensor_id}",
                )
            joined.append((measurement, metadata))

        active_joined = [item for item in joined if item[1].is_enabled == "true"]
        if not active_joined:
            target = self.town_code or self.county_code
            raise SourceSchemaError(
                "empty_unexpected",
                f"WRA IoW returned no enabled flood-depth sensors for target {target}",
            )

        joined.sort(
            key=lambda item: (
                item[1].town_name,
                item[1].observatory_identifier,
                item[0].sensor_id,
            )
        )
        records: list[dict[str, str]] = []
        for index, (measurement, metadata) in enumerate(joined, start=1):
            observed_at = _parse_timestamp(
                measurement.timestamp,
                field_name="timestamp",
            ).isoformat(timespec="seconds")
            records.append(
                {
                    "排序": str(index),
                    "感測器代碼": measurement.sensor_id,
                    "觀測站代碼": metadata.observatory_identifier,
                    "縣市代碼": metadata.county_code,
                    "鄉鎮代碼": metadata.area_code,
                    "縣市": metadata.county_name,
                    "鄉鎮": metadata.town_name,
                    "感測器名稱": unescape(metadata.sensor_full_name),
                    "觀測站名稱": unescape(metadata.observatory_name),
                    "維運單位": unescape(metadata.organization_name),
                    "類別": metadata.category,
                    "地址": "",
                    "緯度": metadata.latitude,
                    "經度": metadata.longitude,
                    "啟用狀態": metadata.is_enabled,
                    "水情時間": measurement.timestamp,
                    "水情時間ISO": observed_at,
                    "目前感測值": f"{measurement.latest_value} {metadata.unit}",
                    "目前感測值數值": _numeric_text(measurement.latest_value),
                    "目前感測值單位": metadata.unit,
                    "資料產出時間": measurement.timestamp,
                    "資料產出時間ISO": observed_at,
                    "抓取時間": fetched_at,
                    "資料模式": "live",
                    "資料來源": source_url,
                }
            )

        latest_observation = max(
            _parse_timestamp(measurement.timestamp, field_name="timestamp")
            for measurement, _metadata in active_joined
        )
        age_minutes = max(0.0, (now - latest_observation).total_seconds() / 60)
        outcome: Literal["ok", "stale"] = "stale" if age_minutes > self.max_age_minutes else "ok"
        content_hash = hashlib.sha256()
        for content in [*latest_contents, *catalog_contents]:
            content_hash.update(content)

        return SourceResult(
            dataset=self.dataset,
            records=records,
            provenance=SourceProvenance(
                source_kind="api",
                outcome=outcome,
                authority="Water Resources Agency, Taiwan",
                dataset_id=f"{LATEST_DATASET_ID}+{CATALOG_DATASET_ID}",
                source_url=source_url,
                fetched_at=fetched_at,
                schema_version=SCHEMA_VERSION,
                content_sha256=content_hash.hexdigest(),
            ),
        )


__all__ = [
    "CATALOG_DATASET_ID",
    "LATEST_DATASET_ID",
    "WraFloodSensorAdapter",
    "WraIowLatestMeasurement",
    "WraIowSensorMetadata",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test the official WRA IoW flood-depth contracts.",
    )
    parser.add_argument("--county", default="10010")
    parser.add_argument("--town-code")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-age-minutes", type=float, default=90)
    args = parser.parse_args()
    settings = get_settings()
    try:
        result = WraFloodSensorAdapter(
            county_code=args.county,
            town_code=args.town_code,
            base_url=settings.wra_open_data_api_url,
            timeout_seconds=args.timeout_seconds,
            max_age_minutes=args.max_age_minutes,
        ).collect()
    except SourceAdapterError as exc:
        raise SystemExit(
            f"[ERROR] WRA IoW flood-sensor smoke failed kind={exc.kind}: {exc}"
        ) from exc
    print(
        f"[OK] dataset={result.dataset} records={len(result.records)} "
        f"outcome={result.provenance.outcome} fetched_at={result.provenance.fetched_at} "
        f"sha256={result.provenance.content_sha256}"
    )
    if result.provenance.outcome != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
