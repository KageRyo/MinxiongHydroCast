"""Build Minxiong operational features from validated snapshot records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from floodcastminxiong.spatial.locations import (
    flood_sensor_location,
    rain_gauge_location,
)

MINXIONG_FEATURE_FIELDS = [
    "feature_time",
    "county",
    "township",
    "data_mode",
    "data_ready",
    "upstream_health",
    "rain_gauge_count",
    "rain_gauge_location_ids",
    "latest_rain_observed_at",
    "max_rain_1h_mm",
    "max_rain_24h_mm",
    "flood_sensor_count",
    "flood_sensor_location_ids",
    "latest_flood_observed_at",
    "max_water_level_cm",
    "rainfall_alert_count",
    "active_rainfall_alert_count",
    "alert_locations",
    "qpe_available",
    "qpe_accumulation_mm",
    "experimental_forecast_included",
]


def _float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _maximum(records: list[dict[str, str]], field: str) -> str:
    values = [_float(record.get(field)) for record in records]
    numeric = [value for value in values if value is not None]
    return f"{max(numeric):g}" if numeric else ""


def _max_water_level_cm(records: list[dict[str, str]]) -> str:
    values: list[float] = []
    for record in records:
        value = _float(record.get("目前感測值數值"))
        unit = record.get("目前感測值單位", "")
        if value is None:
            continue
        if unit == "cm":
            values.append(value)
        elif unit == "m":
            values.append(value * 100)
        elif unit == "mm":
            values.append(value / 10)
    return f"{max(values):g}" if values else ""


def _latest(records: list[dict[str, str]], field: str) -> str:
    values = [record.get(field, "") for record in records if record.get(field)]
    return max(values) if values else ""


def build_minxiong_feature(
    records: dict[str, list[dict[str, str]]],
    *,
    mode: str,
    upstream_health: dict[str, str],
    now: datetime,
) -> dict[str, Any]:
    rain = [
        record
        for record in records["rain_gauges"]
        if "民雄鄉" in record.get("行政區", "")
    ]
    flood = [
        record
        for record in records["flood_sensors"]
        if record.get("鄉鎮", "").strip() == "民雄鄉"
    ]
    alerts = [
        record
        for record in records["rainfall_alerts"]
        if "民雄鄉" in record.get("地區", "")
        or "民雄鄉" in record.get("影響村落", "")
    ]
    active_alerts = [
        record
        for record in alerts
        if record.get("警戒", "").strip() not in {"", "未知", "未達警戒"}
    ]
    rain_locations = sorted(
        {rain_gauge_location(record)["location_id"] for record in rain}
    )
    flood_locations = sorted(
        {flood_sensor_location(record)["location_id"] for record in flood}
    )
    upstream_ready = all(state == "healthy" for state in upstream_health.values())
    return {
        "feature_time": now.isoformat(timespec="seconds"),
        "county": "嘉義縣",
        "township": "民雄鄉",
        "data_mode": mode,
        "data_ready": str(upstream_ready).lower(),
        "upstream_health": ";".join(
            f"{name}={state}" for name, state in sorted(upstream_health.items())
        ),
        "rain_gauge_count": str(len(rain)),
        "rain_gauge_location_ids": ";".join(rain_locations),
        "latest_rain_observed_at": _latest(rain, "水情時間ISO"),
        "max_rain_1h_mm": _maximum(rain, "1小時累積雨量mm"),
        "max_rain_24h_mm": _maximum(rain, "24小時累積雨量mm"),
        "flood_sensor_count": str(len(flood)),
        "flood_sensor_location_ids": ";".join(flood_locations),
        "latest_flood_observed_at": _latest(flood, "水情時間ISO"),
        "max_water_level_cm": _max_water_level_cm(flood),
        "rainfall_alert_count": str(len(alerts)),
        "active_rainfall_alert_count": str(len(active_alerts)),
        "alert_locations": ";".join(
            sorted({record.get("地區", "") for record in alerts if record.get("地區")})
        ),
        "qpe_available": "false",
        "qpe_accumulation_mm": "",
        "experimental_forecast_included": "false",
    }
