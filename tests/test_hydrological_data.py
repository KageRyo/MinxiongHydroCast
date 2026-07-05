from floodcasttw.ingestion.hydrological_data import (
    extract_production_time,
    parse_flood_rows,
    parse_rain_rows,
)


def test_extract_production_time_from_page_text():
    text = "即時雨量\n資料產出時間： 2026-07-05 09:37\n排序"

    assert extract_production_time(text) == "2026-07-05 09:37"


def test_parse_rain_rows_skips_header_and_maps_fields():
    rows = [
        ["排序", "行政區", "雨量站", "水情時間", "1小時累積", "24小時累積"],
        ["64", "嘉義縣番路鄉", "小公田(2)", "07-05 09:20", "0", "0"],
    ]

    records = parse_rain_rows(
        rows,
        production_time="2026-07-05 09:37",
        fetched_at="2026-07-05T09:40:00",
        mode="live",
        source_url="https://example.test/rain",
    )

    assert records == [
        {
            "排序": "64",
            "行政區": "嘉義縣番路鄉",
            "雨量站": "小公田(2)",
            "水情時間": "07-05 09:20",
            "1小時累積雨量": "0",
            "24小時累積雨量": "0",
            "資料產出時間": "2026-07-05 09:37",
            "抓取時間": "2026-07-05T09:40:00",
            "資料模式": "live",
            "資料來源": "https://example.test/rain",
        }
    ]


def test_parse_flood_rows_handles_no_data():
    rows = [
        [
            "排序",
            "縣市",
            "鄉鎮",
            "感測器名稱",
            "地址",
            "水情時間",
            "目前感測值",
        ],
        ["無資料"],
    ]

    assert (
        parse_flood_rows(
            rows,
            production_time="2026-07-05 09:37",
            fetched_at="2026-07-05T09:40:00",
            mode="live",
            source_url="https://example.test/flood",
        )
        == []
    )


def test_parse_flood_rows_maps_sensor_fields():
    rows = [
        [
            "1",
            "嘉義縣",
            "太保市",
            "埤麻腳社區",
            "嘉義縣太保市測試地址",
            "07-05 09:20",
            "0 公分",
        ]
    ]

    records = parse_flood_rows(
        rows,
        production_time="2026-07-05 09:37",
        fetched_at="2026-07-05T09:40:00",
        mode="live",
        source_url="https://example.test/flood",
    )

    assert records[0]["感測器名稱"] == "埤麻腳社區"
    assert records[0]["目前感測值"] == "0 公分"
    assert records[0]["資料模式"] == "live"
