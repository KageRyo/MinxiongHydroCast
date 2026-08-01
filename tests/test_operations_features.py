from datetime import datetime
from zoneinfo import ZoneInfo

from minxionghydrocast.operations.features import (
    build_minxiong_feature,
    build_region_feature,
)
from minxionghydrocast.region_profiles import load_region_profile

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def test_build_minxiong_feature_filters_region_and_links_stable_locations():
    records = {
        "rain_gauges": [
            {
                "行政區": "嘉義縣民雄鄉",
                "雨量站": "民雄",
                "水情時間ISO": "2026-07-11T10:00:00+08:00",
                "1小時累積雨量mm": "12.5",
                "24小時累積雨量mm": "30",
            },
            {
                "行政區": "嘉義縣太保市",
                "雨量站": "太保",
                "水情時間ISO": "2026-07-11T10:00:00+08:00",
                "1小時累積雨量mm": "99",
                "24小時累積雨量mm": "99",
            },
        ],
        "flood_sensors": [
            {
                "縣市": "嘉義縣",
                "鄉鎮": "民雄鄉",
                "感測器名稱": "中樂村",
                "地址": "嘉義縣民雄鄉中樂村",
                "水情時間ISO": "2026-07-11T09:55:00+08:00",
                "目前感測值數值": "0.2",
                "目前感測值單位": "m",
            },
            {
                "縣市": "嘉義縣",
                "鄉鎮": "民雄鄉",
                "感測器名稱": "停用測站",
                "地址": "嘉義縣民雄鄉",
                "啟用狀態": "false",
                "水情時間ISO": "2026-07-11T10:00:00+08:00",
                "目前感測值數值": "999",
                "目前感測值單位": "cm",
            },
        ],
        "rainfall_alerts": [
            {
                "地區": "嘉義 民雄鄉",
                "影響村落": "民雄鄉-中樂村",
                "警戒": "警戒中",
            }
        ],
    }

    feature = build_minxiong_feature(
        records,
        mode="live",
        upstream_health={
            "rainfall_alerts": "healthy",
            "rain_gauges": "healthy",
            "flood_sensors": "healthy",
        },
        now=datetime(2026, 7, 11, 10, 5, tzinfo=TAIPEI_TZ),
    )

    assert feature["data_ready"] == "true"
    assert feature["coverage_ready"] == "true"
    assert feature["coverage_gaps"] == ""
    assert feature["rain_gauge_count"] == "1"
    assert feature["max_rain_1h_mm"] == "12.5"
    assert feature["max_rain_24h_mm"] == "30"
    assert feature["flood_sensor_count"] == "1"
    assert feature["max_water_level_cm"] == "20"
    assert feature["active_rainfall_alert_count"] == "1"
    assert feature["rain_gauge_location_ids"].startswith("rain_gauge_")
    assert feature["flood_sensor_location_ids"].startswith("flood_sensor_")
    assert feature["qpe_available"] == "false"


def test_build_minxiong_feature_reports_missing_target_coverage():
    feature = build_minxiong_feature(
        {
            "rain_gauges": [{"行政區": "嘉義縣太保市", "雨量站": "太保"}],
            "flood_sensors": [{"縣市": "嘉義縣", "鄉鎮": "太保市"}],
            "rainfall_alerts": [],
        },
        mode="live",
        upstream_health={
            "rainfall_alerts": "healthy",
            "rain_gauges": "healthy",
            "flood_sensors": "healthy",
        },
        now=datetime(2026, 7, 11, 10, 5, tzinfo=TAIPEI_TZ),
    )

    assert feature["data_ready"] == "false"
    assert feature["coverage_ready"] == "false"
    assert feature["coverage_gaps"] == "rain_gauges=0<1;flood_sensors=0<1"


def test_build_region_feature_uses_selected_profile_identity_and_filters():
    feature = build_region_feature(
        {
            "rain_gauges": [
                {
                    "行政區": "Example County Example District",
                    "雨量站": "Example Gauge",
                    "水情時間ISO": "2026-07-11T10:00:00+08:00",
                    "1小時累積雨量mm": "4",
                    "24小時累積雨量mm": "8",
                },
                {"行政區": "嘉義縣民雄鄉", "雨量站": "民雄"},
            ],
            "flood_sensors": [
                {
                    "縣市": "Example County",
                    "鄉鎮": "Example District",
                    "感測器名稱": "Example Sensor",
                    "水情時間ISO": "2026-07-11T10:00:00+08:00",
                    "目前感測值數值": "10",
                    "目前感測值單位": "cm",
                },
                {"縣市": "嘉義縣", "鄉鎮": "民雄鄉", "感測器名稱": "民雄"},
            ],
            "rainfall_alerts": [
                {
                    "鄉鎮代碼": "99999999",
                    "地區": "Example District",
                    "警戒": "警戒中",
                }
            ],
        },
        profile=load_region_profile("example-region"),
        mode="live",
        upstream_health={
            "rainfall_alerts": "healthy",
            "rain_gauges": "healthy",
            "flood_sensors": "healthy",
        },
        now=datetime(2026, 7, 11, 10, 5, tzinfo=TAIPEI_TZ),
    )

    assert feature["region_id"] == "example-region"
    assert feature["region_name"] == "Example Region"
    assert feature["township"] == "Example District"
    assert feature["rain_gauge_count"] == "1"
    assert feature["flood_sensor_count"] == "1"
    assert feature["rainfall_alert_count"] == "1"
    assert feature["coverage_ready"] == "true"
