"""Dataset schema definitions."""

from __future__ import annotations

RAIN_GAUGE_REQUIRED_FIELDS = {
    "排序",
    "行政區",
    "雨量站",
    "雨量站代碼",
    "水情時間",
    "水情時間ISO",
    "1小時累積雨量",
    "1小時累積雨量mm",
    "24小時累積雨量",
    "24小時累積雨量mm",
    "緯度",
    "經度",
    "資料產出時間",
    "資料產出時間ISO",
    "抓取時間",
    "資料模式",
    "資料來源",
}

FLOOD_SENSOR_REQUIRED_FIELDS = {
    "排序",
    "縣市",
    "鄉鎮",
    "感測器名稱",
    "地址",
    "水情時間",
    "水情時間ISO",
    "目前感測值",
    "目前感測值數值",
    "目前感測值單位",
    "資料產出時間",
    "資料產出時間ISO",
    "抓取時間",
    "資料模式",
    "資料來源",
}

RAINFALL_ALERT_REQUIRED_FIELDS = {
    "地區",
    "警戒",
    "影響村落",
    "1h雨量",
    "3h雨量",
    "6h雨量",
    "抓取時間",
    "資料模式",
}

SHELTER_REQUIRED_FIELDS = {
    "鄉鎮市",
    "避難所名稱",
    "避難所地址",
    "避難所聯絡人",
    "收容人數",
    "來源檔案",
    "抽取時間",
}

PUMPING_STATION_REQUIRED_FIELDS = {
    "項次",
    "鄉鎮市",
    "地點",
    "座標X",
    "座標Y",
    "流入排水名稱",
    "數量",
}

LOCATION_REFERENCE_REQUIRED_FIELDS = {
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
}
