"""Location-reference builders for hydrology and flood-risk datasets."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from floodcastminxiong.io.csv_utils import write_csv
from floodcastminxiong.spatial.admin import admin_unit_key, extract_admin_parts
from floodcastminxiong.spatial.coordinates import normalize_coordinates

LOCATION_FIELDNAMES = [
    "location_id",
    "source_type",
    "source_name",
    "county",
    "township",
    "village",
    "address",
    "latitude",
    "longitude",
    "crs",
    "coordinate_source",
    "admin_unit_key",
]


def stable_location_id(source_type: str, *parts: str) -> str:
    normalized = "|".join(part.strip().lower() for part in parts if part and part.strip())
    digest = hashlib.sha1(f"{source_type}|{normalized}".encode("utf-8")).hexdigest()[:12]
    return f"{source_type}_{digest}"


def rain_gauge_location(record: dict[str, str]) -> dict[str, str]:
    admin = extract_admin_parts(record.get("行政區", ""))
    source_name = record.get("雨量站", "")
    station_id = record.get("雨量站代碼", "")
    latitude, longitude, crs = normalize_coordinates(
        record.get("latitude") or record.get("緯度"),
        record.get("longitude") or record.get("經度"),
    )
    return {
        "location_id": stable_location_id(
            "rain_gauge",
            station_id or admin["county"],
            "" if station_id else admin["township"],
            "" if station_id else source_name,
        ),
        "source_type": "rain_gauge",
        "source_name": source_name,
        "county": admin["county"],
        "township": admin["township"],
        "village": admin["village"],
        "address": "",
        "latitude": latitude,
        "longitude": longitude,
        "crs": crs,
        "coordinate_source": "source" if crs == "WGS84" else "",
        "admin_unit_key": admin_unit_key(admin["county"], admin["township"], admin["village"]),
    }


def flood_sensor_location(record: dict[str, str]) -> dict[str, str]:
    address = record.get("地址", "")
    address_admin = extract_admin_parts(address)
    county = record.get("縣市", "") or address_admin["county"]
    township = record.get("鄉鎮", "") or address_admin["township"]
    village = address_admin["village"]
    source_name = record.get("感測器名稱", "")
    sensor_id = record.get("感測器代碼", "")
    latitude, longitude, crs = normalize_coordinates(
        record.get("latitude") or record.get("緯度"),
        record.get("longitude") or record.get("經度"),
    )
    return {
        "location_id": stable_location_id(
            "flood_sensor",
            sensor_id or county,
            "" if sensor_id else township,
            "" if sensor_id else source_name,
            "" if sensor_id else address,
        ),
        "source_type": "flood_sensor",
        "source_name": source_name,
        "county": county,
        "township": township,
        "village": village,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "crs": crs,
        "coordinate_source": "source" if crs == "WGS84" else "",
        "admin_unit_key": admin_unit_key(county, township, village),
    }


def pumping_station_location(record: dict[str, str]) -> dict[str, str]:
    county = ""
    township = record.get("鄉鎮市", "") or record.get("鄉鎮(市)", "")
    source_name = record.get("地點", "")
    latitude, longitude, crs = normalize_coordinates(
        twd97_x=record.get("座標X") or record.get("座標 X"),
        twd97_y=record.get("座標Y") or record.get("座標 Y"),
    )
    return {
        "location_id": stable_location_id("pumping_station", township, source_name),
        "source_type": "pumping_station",
        "source_name": source_name,
        "county": county,
        "township": township,
        "village": "",
        "address": source_name,
        "latitude": latitude,
        "longitude": longitude,
        "crs": crs,
        "coordinate_source": "TWD97_TM2_121" if crs else "",
        "admin_unit_key": admin_unit_key(county, township, ""),
    }


def shelter_location(record: dict[str, str]) -> dict[str, str]:
    admin = extract_admin_parts(f"{record.get('鄉鎮市', '')}{record.get('避難所地址', '')}")
    source_name = record.get("避難所名稱", "")
    address = record.get("避難所地址", "")
    township = record.get("鄉鎮市", "") or admin["township"]
    return {
        "location_id": stable_location_id("shelter", admin["township"], source_name, address),
        "source_type": "shelter",
        "source_name": source_name,
        "county": admin["county"],
        "township": township,
        "village": admin["village"],
        "address": address,
        "latitude": "",
        "longitude": "",
        "crs": "",
        "coordinate_source": "",
        "admin_unit_key": admin_unit_key(admin["county"], township, admin["village"]),
    }


def flood_risk_area_location(record: dict[str, str]) -> dict[str, str]:
    area = record.get("鄉鎮市區-村里", "")
    admin = extract_admin_parts(area)
    return {
        "location_id": stable_location_id("flood_risk_area", area),
        "source_type": "flood_risk_area",
        "source_name": area,
        "county": admin["county"],
        "township": admin["township"],
        "village": admin["village"],
        "address": record.get("避難處所地址", ""),
        "latitude": "",
        "longitude": "",
        "crs": "",
        "coordinate_source": "",
        "admin_unit_key": admin_unit_key(admin["county"], admin["township"], admin["village"]),
    }


def read_csv_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def dedupe_locations(locations: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for location in locations:
        location_id = location["location_id"]
        if location_id in seen:
            continue
        seen.add(location_id)
        deduped.append(location)
    return deduped


def build_location_reference(
    rain_records: list[dict[str, str]] | None = None,
    flood_records: list[dict[str, str]] | None = None,
    pumping_station_records: list[dict[str, str]] | None = None,
    shelter_records: list[dict[str, str]] | None = None,
    flood_risk_area_records: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    locations = [
        *(rain_gauge_location(record) for record in (rain_records or [])),
        *(flood_sensor_location(record) for record in (flood_records or [])),
        *(pumping_station_location(record) for record in (pumping_station_records or [])),
        *(shelter_location(record) for record in (shelter_records or [])),
        *(flood_risk_area_location(record) for record in (flood_risk_area_records or [])),
    ]
    return dedupe_locations(locations)


def write_location_reference(locations: list[dict[str, str]], output_path: Path) -> int:
    return write_csv(locations, output_path, LOCATION_FIELDNAMES)
