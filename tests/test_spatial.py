import csv
from pathlib import Path

from floodcastminxiong.spatial.admin import admin_unit_key, extract_admin_parts
from floodcastminxiong.spatial.coordinates import (
    is_valid_taiwan_wgs84,
    normalize_coordinates,
    twd97_tm2_to_wgs84,
)
from floodcastminxiong.spatial.grid import CHIAYI_COUNTY_GRID, MINXIONG_GRID
from floodcastminxiong.spatial.locations import (
    build_location_reference,
    flood_sensor_location,
    rain_gauge_location,
    write_location_reference,
)


def test_extract_admin_parts_without_county_bleed():
    parts = extract_admin_parts("嘉義縣民雄鄉中樂村")

    assert parts == {"county": "嘉義縣", "township": "民雄鄉", "village": "中樂村"}
    assert admin_unit_key(**parts) == "嘉義縣|民雄鄉|中樂村"


def test_twd97_to_wgs84_converts_taiwan_coordinates():
    latitude, longitude = twd97_tm2_to_wgs84(250000, 2600000)

    assert 23.0 < latitude < 24.0
    assert 120.9 < longitude < 121.1
    assert is_valid_taiwan_wgs84(latitude, longitude)


def test_normalize_coordinates_prefers_valid_wgs84():
    latitude, longitude, crs = normalize_coordinates("23.55", "120.45", "250000", "2600000")

    assert (latitude, longitude, crs) == ("23.550000", "120.450000", "WGS84")


def test_grid_spec_returns_stable_cell_ids():
    assert CHIAYI_COUNTY_GRID.contains(23.55, 120.45)
    assert CHIAYI_COUNTY_GRID.cell_id(23.55, 120.45).startswith("chiayi_county")
    assert MINXIONG_GRID.contains(23.55, 120.45)


def test_hydrology_location_builders_generate_admin_keys():
    rain = rain_gauge_location({"行政區": "嘉義縣民雄鄉", "雨量站": "民雄"})
    flood = flood_sensor_location(
        {
            "縣市": "嘉義縣",
            "鄉鎮": "民雄鄉",
            "感測器名稱": "CYC098民雄鄉中樂村民雄",
            "地址": "嘉義縣民雄鄉中樂村保安宮旁",
        }
    )

    assert rain["source_type"] == "rain_gauge"
    assert rain["admin_unit_key"] == "嘉義縣|民雄鄉"
    assert flood["source_type"] == "flood_sensor"
    assert flood["admin_unit_key"] == "嘉義縣|民雄鄉|中樂村"
    assert flood["location_id"].startswith("flood_sensor_")


def test_rain_gauge_location_prefers_official_station_id_for_stability():
    original = rain_gauge_location(
        {
            "行政區": "嘉義縣民雄鄉",
            "雨量站": "民雄",
            "雨量站代碼": "C0M760",
        }
    )
    renamed = rain_gauge_location(
        {
            "行政區": "嘉義縣民雄鄉",
            "雨量站": "民雄氣象站",
            "雨量站代碼": "C0M760",
        }
    )

    assert original["location_id"] == renamed["location_id"]


def test_flood_sensor_location_prefers_official_sensor_id_for_stability():
    original = flood_sensor_location(
        {
            "縣市": "嘉義縣",
            "鄉鎮": "民雄鄉",
            "感測器名稱": "CYC136 民雄鄉大崎村淹水深度",
            "感測器代碼": "00707a34-700c-4e01-b091-396378c234f6",
        }
    )
    renamed = flood_sensor_location(
        {
            "縣市": "嘉義縣",
            "鄉鎮": "民雄鄉",
            "感測器名稱": "CYC136 民雄鄉大崎村積水深度",
            "感測器代碼": "00707a34-700c-4e01-b091-396378c234f6",
        }
    )

    assert original["location_id"] == renamed["location_id"]


def test_build_location_reference_dedupes_and_writes_csv(tmp_path: Path):
    locations = build_location_reference(
        rain_records=[
            {"行政區": "嘉義縣民雄鄉", "雨量站": "民雄"},
            {"行政區": "嘉義縣民雄鄉", "雨量站": "民雄"},
        ],
        flood_records=[
            {
                "縣市": "嘉義縣",
                "鄉鎮": "民雄鄉",
                "感測器名稱": "CYC098民雄鄉中樂村民雄",
                "地址": "嘉義縣民雄鄉中樂村保安宮旁",
            }
        ],
    )
    output = tmp_path / "location_reference.csv"
    count = write_location_reference(locations, output)

    assert count == 2
    with output.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["source_type"] for row in rows] == ["rain_gauge", "flood_sensor"]
