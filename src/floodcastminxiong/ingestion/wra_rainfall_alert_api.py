"""WRA official rainfall-warning source adapter."""

from __future__ import annotations

import argparse
import hashlib
import math
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from floodcastminxiong.config import get_settings
from floodcastminxiong.ingestion.http_client import ReliableJsonClient
from floodcastminxiong.ingestion.source_adapter import (
    SourceAdapterError,
    SourceProvenance,
    SourceRequestError,
    SourceResult,
    SourceSchemaError,
)

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DATASET_NAME = "rainfall_alerts"
DATASET_ID = "WRA-Rainfall-Warning-v2"
SCHEMA_VERSION = "wra-rainfall-warning-v2-v1"
DEFAULT_BASE_URL = "https://fhy.wra.gov.tw/OpenApiv3"
DEFAULT_ENDPOINT = f"{DEFAULT_BASE_URL}/v2/Rainfall/Warning"

RainfallAmount = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
WarningLevel = Annotated[int, Field(strict=True, ge=1, le=2)]


class WraSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class WraRainfallWarning(WraSchema):
    station_no: str = Field(alias="StationNo", min_length=1)
    city_code: str = Field(alias="CityCode", min_length=1)
    town_code: str = Field(alias="TownCode", min_length=1)
    observed_at: str = Field(alias="Time", min_length=1)
    m10: RainfallAmount = Field(alias="M10")
    h1: RainfallAmount = Field(alias="H1")
    h3: RainfallAmount = Field(alias="H3")
    h6: RainfallAmount = Field(alias="H6")
    h12: RainfallAmount = Field(alias="H12")
    h24: RainfallAmount = Field(alias="H24")
    warning_level: WarningLevel = Field(alias="WarningLevel")
    affected_area: str = Field(alias="AffectedArea")

    # WRA documents location codes as opaque strings, without a stable length contract.
    @field_validator("station_no", "city_code", "town_code")
    @classmethod
    def identifier_is_not_whitespace(cls, value: str) -> str:
        if not value.strip() or value != value.strip():
            raise ValueError("identifier must be a non-blank trimmed string")
        return value


class WraRainfallWarningResponse(WraSchema):
    updated_at: str | None = Field(alias="UpdataTime")
    data: list[WraRainfallWarning] = Field(alias="Data")


def _parse_local_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SourceSchemaError(
            "schema_drift",
            "WRA rainfall-warning observation timestamp is invalid",
        ) from exc
    if parsed.tzinfo is not None:
        raise SourceSchemaError(
            "schema_drift",
            "WRA rainfall-warning observation timestamp unexpectedly has a timezone",
        )
    return parsed.replace(tzinfo=TAIPEI_TZ)


def _rainfall(value: float) -> str:
    if not math.isfinite(value) or value < 0:
        raise SourceSchemaError(
            "schema_drift",
            "WRA rainfall-warning amount is not a finite non-negative number",
        )
    return f"{value:g}"


def warning_record(
    warning: WraRainfallWarning,
    *,
    fetched_at: str,
    source_url: str,
) -> dict[str, str]:
    observed_at = _parse_local_time(warning.observed_at)
    affected_area = warning.affected_area.strip()
    return {
        "雨量站代碼": warning.station_no,
        "縣市代碼": warning.city_code,
        "鄉鎮代碼": warning.town_code,
        "地區": affected_area or f"{warning.city_code}/{warning.town_code}",
        "水情時間": warning.observed_at,
        "水情時間ISO": observed_at.isoformat(timespec="seconds"),
        "警戒": f"{warning.warning_level}級警戒",
        "警戒級別": str(warning.warning_level),
        "影響村落": warning.affected_area,
        "10分鐘雨量mm": _rainfall(warning.m10),
        "1小時雨量mm": _rainfall(warning.h1),
        "3小時雨量mm": _rainfall(warning.h3),
        "6小時雨量mm": _rainfall(warning.h6),
        "12小時雨量mm": _rainfall(warning.h12),
        "24小時雨量mm": _rainfall(warning.h24),
        "抓取時間": fetched_at,
        "資料模式": "live",
        "資料來源": source_url,
    }


class WraRainfallAlertAdapter:
    dataset = DATASET_NAME

    def __init__(
        self,
        *,
        api_key: str,
        county_code: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 30,
        max_age_minutes: float = 30,
        client: ReliableJsonClient | None = None,
        now: datetime | None = None,
    ) -> None:
        if max_age_minutes < 0:
            raise ValueError("maximum source age must not be negative")
        self.api_key = api_key
        self.county_code = county_code
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_age_minutes = max_age_minutes
        self.client = client or ReliableJsonClient()
        self.now = now

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/v2/Rainfall/Warning"

    @staticmethod
    def params() -> dict[str, str]:
        return {"$top": "1000", "$skip": "0"}

    def redacted_url(self) -> str:
        return f"{self.endpoint}?{urlencode(self.params())}"

    def collect(self) -> SourceResult:
        if not self.api_key:
            raise SourceRequestError("authentication", "missing WRA_API_KEY")

        now = (self.now or datetime.now(TAIPEI_TZ)).astimezone(TAIPEI_TZ)
        fetched_at = now.isoformat(timespec="seconds")
        response = self.client.get_json(
            self.endpoint,
            params=self.params(),
            headers={"apikey": self.api_key},
            timeout_seconds=self.timeout_seconds,
            redacted_url=self.redacted_url(),
        )
        try:
            payload = WraRainfallWarningResponse.model_validate(response.payload)
        except ValidationError as exc:
            raise SourceSchemaError(
                "schema_drift",
                f"WRA rainfall-warning response contract changed: {exc.errors()[0]['msg']}",
            ) from exc
        if payload.updated_at is not None:
            _parse_local_time(payload.updated_at)
        for warning in payload.data:
            _parse_local_time(warning.observed_at)

        warnings = [warning for warning in payload.data if warning.city_code == self.county_code]
        source_url = response.url
        checksum = hashlib.sha256(response.content).hexdigest()
        if not warnings:
            return SourceResult(
                dataset=self.dataset,
                records=[],
                provenance=SourceProvenance(
                    source_kind="api",
                    outcome="empty",
                    authority="Water Resources Agency, Taiwan",
                    dataset_id=DATASET_ID,
                    source_url=source_url,
                    fetched_at=fetched_at,
                    schema_version=SCHEMA_VERSION,
                    content_sha256=checksum,
                ),
            )

        records = [
            warning_record(
                warning,
                fetched_at=fetched_at,
                source_url=source_url,
            )
            for warning in warnings
        ]
        latest = max(_parse_local_time(warning.observed_at) for warning in warnings)
        age_minutes = max(0.0, (now - latest).total_seconds() / 60)
        outcome: Literal["ok", "stale"] = "stale" if age_minutes > self.max_age_minutes else "ok"
        return SourceResult(
            dataset=self.dataset,
            records=records,
            provenance=SourceProvenance(
                source_kind="api",
                outcome=outcome,
                authority="Water Resources Agency, Taiwan",
                dataset_id=DATASET_ID,
                source_url=source_url,
                fetched_at=fetched_at,
                schema_version=SCHEMA_VERSION,
                content_sha256=checksum,
            ),
        )


__all__ = [
    "WraRainfallAlertAdapter",
    "WraRainfallWarningResponse",
    "SourceAdapterError",
]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smoke-test the official WRA rainfall-warning contract.",
    )
    parser.add_argument("--county", default="10010")
    parser.add_argument("--timeout-seconds", type=float, default=30)
    parser.add_argument("--max-age-minutes", type=float, default=30)
    args = parser.parse_args()
    settings = get_settings()
    try:
        result = WraRainfallAlertAdapter(
            api_key=settings.wra_api_key,
            county_code=args.county,
            base_url=settings.wra_api_url,
            timeout_seconds=args.timeout_seconds,
            max_age_minutes=args.max_age_minutes,
        ).collect()
    except SourceAdapterError as exc:
        raise SystemExit(
            f"[ERROR] WRA rainfall-warning smoke failed kind={exc.kind}: {exc}"
        ) from exc
    print(
        f"[OK] dataset={result.dataset} records={len(result.records)} "
        f"outcome={result.provenance.outcome} fetched_at={result.provenance.fetched_at} "
        f"sha256={result.provenance.content_sha256}"
    )
    if result.provenance.outcome not in {"ok", "empty"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
