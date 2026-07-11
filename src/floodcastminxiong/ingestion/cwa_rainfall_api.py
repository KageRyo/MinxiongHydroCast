"""CWA O-A0002-001 official rain-gauge source adapter."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime
from typing import Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from floodcastminxiong.config import get_settings
from floodcastminxiong.ingestion.cwa_history import redact_authorization_url
from floodcastminxiong.ingestion.http_client import ReliableJsonClient
from floodcastminxiong.ingestion.source_adapter import (
    SourceAdapterError,
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceSchemaError,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DATASET_NAME = "rain_gauges"
DATA_ID = "O-A0002-001"
SCHEMA_VERSION = "cwa-o-a0002-001-v1"
EXPECTED_RESULT_FIELDS = {
    "StationName",
    "StationId",
    "Maintainer",
    "CoordinateName",
    "CoordinateFormat",
    "StationLatitude",
    "StationLongitude",
    "StationAltitude",
    "CountyName",
    "TownName",
    "CountyCode",
    "TownCode",
    "Precipitation",
}
INVALID_PRECIPITATION = {-99.0, -999.0, -1.0}


class CwaSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class CwaResultField(CwaSchema):
    id: str
    type: Literal["String"]


class CwaResult(CwaSchema):
    resource_id: Literal[DATA_ID]
    fields: list[CwaResultField]


class CwaObsTime(CwaSchema):
    date_time: str = Field(alias="DateTime")


class CwaCoordinate(CwaSchema):
    coordinate_name: str = Field(alias="CoordinateName")
    coordinate_format: Literal["decimal degrees"] = Field(alias="CoordinateFormat")
    latitude: str = Field(alias="StationLatitude")
    longitude: str = Field(alias="StationLongitude")


class CwaGeoInfo(CwaSchema):
    coordinates: list[CwaCoordinate] = Field(alias="Coordinates", min_length=1)
    altitude: str = Field(alias="StationAltitude")
    county_name: str = Field(alias="CountyName")
    town_name: str = Field(alias="TownName")
    county_code: str = Field(alias="CountyCode")
    town_code: str = Field(alias="TownCode")


class CwaPrecipitation(CwaSchema):
    precipitation: str = Field(alias="Precipitation")


class CwaRainfallElement(CwaSchema):
    now: CwaPrecipitation = Field(alias="Now")
    past_10_min: CwaPrecipitation = Field(alias="Past10Min")
    past_1_hour: CwaPrecipitation = Field(alias="Past1hr")
    past_3_hours: CwaPrecipitation = Field(alias="Past3hr")
    past_6_hours: CwaPrecipitation = Field(alias="Past6Hr")
    past_12_hours: CwaPrecipitation = Field(alias="Past12hr")
    past_24_hours: CwaPrecipitation = Field(alias="Past24hr")
    past_2_days: CwaPrecipitation = Field(alias="Past2days")
    past_3_days: CwaPrecipitation = Field(alias="Past3days")


class CwaStation(CwaSchema):
    station_name: str = Field(alias="StationName")
    station_id: str = Field(alias="StationId")
    maintainer: str = Field(alias="Maintainer")
    observed_at: CwaObsTime = Field(alias="ObsTime")
    geo_info: CwaGeoInfo = Field(alias="GeoInfo")
    rainfall: CwaRainfallElement = Field(alias="RainfallElement")


class CwaRecords(CwaSchema):
    stations: list[CwaStation] = Field(alias="Station")


class CwaRainfallResponse(CwaSchema):
    success: Literal["true"]
    result: CwaResult
    records: CwaRecords

    @model_validator(mode="after")
    def result_fields_match_contract(self) -> CwaRainfallResponse:
        actual = {field.id for field in self.result.fields}
        if actual != EXPECTED_RESULT_FIELDS:
            missing = sorted(EXPECTED_RESULT_FIELDS - actual)
            unexpected = sorted(actual - EXPECTED_RESULT_FIELDS)
            raise ValueError(
                f"result field contract changed; missing={missing}, unexpected={unexpected}"
            )
        return self


def _precipitation(value: str) -> str:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise SourceSchemaError(
            "schema_drift",
            f"CWA {DATA_ID} precipitation is not numeric",
        ) from exc
    if parsed in INVALID_PRECIPITATION or parsed < 0:
        return ""
    return f"{parsed:g}"


def _wgs84(station: CwaStation) -> tuple[str, str]:
    for coordinate in station.geo_info.coordinates:
        if coordinate.coordinate_name.upper() == "WGS84":
            try:
                latitude = float(coordinate.latitude)
                longitude = float(coordinate.longitude)
            except ValueError as exc:
                raise SourceSchemaError(
                    "schema_drift",
                    f"CWA {DATA_ID} WGS84 coordinate is not numeric",
                ) from exc
            if not (20 <= latitude <= 27 and 118 <= longitude <= 123):
                raise SourceSchemaError(
                    "schema_drift",
                    f"CWA {DATA_ID} WGS84 coordinate is outside Taiwan bounds",
                )
            return f"{latitude:.6f}", f"{longitude:.6f}"
    raise SourceSchemaError(
        "schema_drift",
        f"CWA {DATA_ID} station is missing WGS84 coordinates",
    )


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SourceSchemaError(
            "schema_drift",
            f"CWA {DATA_ID} observation timestamp is invalid",
        ) from exc
    if parsed.tzinfo is None:
        raise SourceSchemaError(
            "schema_drift",
            f"CWA {DATA_ID} observation timestamp has no timezone",
        )
    return parsed.astimezone(TAIPEI_TZ)


def station_record(
    station: CwaStation,
    *,
    index: int,
    fetched_at: str,
    source_url: str,
) -> dict[str, str]:
    observed_at = _parse_time(station.observed_at.date_time).isoformat(timespec="seconds")
    latitude, longitude = _wgs84(station)
    one_hour = _precipitation(station.rainfall.past_1_hour.precipitation)
    twenty_four_hours = _precipitation(station.rainfall.past_24_hours.precipitation)
    return {
        "排序": str(index),
        "行政區": f"{station.geo_info.county_name}{station.geo_info.town_name}",
        "雨量站": station.station_name,
        "雨量站代碼": station.station_id,
        "水情時間": station.observed_at.date_time,
        "水情時間ISO": observed_at,
        "1小時累積雨量": one_hour,
        "1小時累積雨量mm": one_hour,
        "24小時累積雨量": twenty_four_hours,
        "24小時累積雨量mm": twenty_four_hours,
        "緯度": latitude,
        "經度": longitude,
        "資料產出時間": station.observed_at.date_time,
        "資料產出時間ISO": observed_at,
        "抓取時間": fetched_at,
        "資料模式": "live",
        "資料來源": source_url,
    }


class CwaRainGaugeAdapter:
    dataset = DATASET_NAME

    def __init__(
        self,
        *,
        authorization: str,
        county_code: str,
        county_name: str = "嘉義縣",
        base_url: str = "",
        timeout_seconds: float = 30,
        max_age_minutes: float = 30,
        client: ReliableJsonClient | None = None,
        now: datetime | None = None,
    ) -> None:
        settings = get_settings()
        self.authorization = authorization
        self.county_code = county_code
        self.county_name = county_name
        self.base_url = (base_url or settings.cwa_rest_api_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_age_minutes = max_age_minutes
        self.client = client or ReliableJsonClient()
        self.now = now

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/{DATA_ID}"

    def params(self) -> dict[str, str]:
        return {
            "Authorization": self.authorization,
            "format": "JSON",
            "CountyName": self.county_name,
        }

    def redacted_url(self) -> str:
        return f"{self.endpoint}?{urlencode({**self.params(), 'Authorization': 'REDACTED'})}"

    def collect(self) -> SourceResult:
        if not self.authorization:
            raise SourceRequestError("authentication", "missing CWA_API_KEY")
        now = (self.now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
        fetched_at = now.isoformat(timespec="seconds")
        response = self.client.get_json(
            self.endpoint,
            params=self.params(),
            timeout_seconds=self.timeout_seconds,
            redacted_url=self.redacted_url(),
        )
        if response.payload.get("success") != "true":
            raise SourceRequestError(
                "http",
                f"CWA {DATA_ID} reported an unsuccessful request",
            )
        try:
            payload = CwaRainfallResponse.model_validate(response.payload)
        except ValidationError as exc:
            raise SourceSchemaError(
                "schema_drift",
                f"CWA {DATA_ID} response contract changed: {exc.errors()[0]['msg']}",
            ) from exc

        stations = [
            station
            for station in payload.records.stations
            if station.geo_info.county_code == self.county_code
        ]
        if not stations:
            raise SourceSchemaError(
                "empty_unexpected",
                f"CWA {DATA_ID} returned no stations for county {self.county_code}",
            )
        source_url = redact_authorization_url(response.url)
        records = [
            station_record(
                station,
                index=index,
                fetched_at=fetched_at,
                source_url=source_url,
            )
            for index, station in enumerate(stations, start=1)
        ]
        latest = max(_parse_time(station.observed_at.date_time) for station in stations)
        age_minutes = max(0.0, (now - latest).total_seconds() / 60)
        outcome: Literal["ok", "stale"] = (
            "stale" if age_minutes > self.max_age_minutes else "ok"
        )
        return SourceResult(
            dataset=self.dataset,
            records=records,
            provenance=SourceProvenance(
                source_kind="api",
                outcome=outcome,
                authority="Central Weather Administration, Taiwan",
                dataset_id=DATA_ID,
                source_url=source_url,
                fetched_at=fetched_at,
                schema_version=SCHEMA_VERSION,
                content_sha256=hashlib.sha256(response.content).hexdigest(),
            ),
        )


__all__ = [
    "CwaRainGaugeAdapter",
    "CwaRainfallResponse",
    "SourceAdapterError",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test the official CWA O-A0002-001 rain-gauge contract.",
    )
    parser.add_argument("--county", default="10010")
    parser.add_argument("--county-name", default="嘉義縣")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-age-minutes", type=float, default=30)
    args = parser.parse_args()
    settings = get_settings()
    try:
        result = CwaRainGaugeAdapter(
            authorization=settings.cwa_api_key,
            county_code=args.county,
            county_name=args.county_name,
            timeout_seconds=args.timeout_seconds,
            max_age_minutes=args.max_age_minutes,
        ).collect()
    except SourceAdapterError as exc:
        raise SystemExit(f"[ERROR] CWA rainfall smoke failed kind={exc.kind}: {exc}") from exc
    print(
        f"[OK] dataset={result.dataset} records={len(result.records)} "
        f"outcome={result.provenance.outcome} fetched_at={result.provenance.fetched_at} "
        f"sha256={result.provenance.content_sha256}"
    )
    if result.provenance.outcome != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
