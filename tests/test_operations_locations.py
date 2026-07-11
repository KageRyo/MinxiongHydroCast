from datetime import datetime
from zoneinfo import ZoneInfo

from floodcastminxiong.operations.locations import build_operational_locations

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def test_operational_locations_include_current_and_static_sources(tmp_path):
    shelters = tmp_path / "shelters.csv"
    shelters.write_text(
        "鄉鎮市,避難所名稱,避難所地址\n"
        "民雄鄉,民雄活動中心,嘉義縣民雄鄉中樂村1號\n",
        encoding="utf-8-sig",
    )
    records = {
        "rain_gauges": [{"行政區": "嘉義縣民雄鄉", "雨量站": "民雄"}],
        "flood_sensors": [
            {
                "縣市": "嘉義縣",
                "鄉鎮": "民雄鄉",
                "感測器名稱": "中樂村",
                "地址": "嘉義縣民雄鄉中樂村",
            }
        ],
    }

    locations = build_operational_locations(
        records,
        mode="live",
        now=datetime(2026, 7, 11, 10, 0, tzinfo=TAIPEI_TZ),
        shelters=shelters,
    )

    assert {location["source_type"] for location in locations} == {
        "rain_gauge",
        "flood_sensor",
        "shelter",
    }
    assert all(location["snapshot_time"] == "2026-07-11T10:00:00+08:00" for location in locations)
    assert all(location["data_mode"] == "live" for location in locations)
