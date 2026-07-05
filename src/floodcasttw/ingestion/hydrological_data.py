"""Rain gauge and flood-sensor ingestion.

The live WRA monitor pages still need a dedicated parser. This module keeps demo output explicit
so downstream development cannot confuse sample data with production captures.
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from floodcasttw.io.csv_utils import write_csv

RAIN_FIELDNAMES = ["測站", "時間", "1H雨量", "累積雨量", "狀態", "抓取時間", "資料模式"]
FLOOD_FIELDNAMES = ["測站", "水位", "狀態", "抓取時間", "資料模式"]

SAMPLE_RAIN = [
    {"測站": "嘉義縣番路鄉", "時間": "09-21 22:00", "1H雨量": "3.5", "累積雨量": "30", "狀態": "未達警戒"},
    {"測站": "嘉義縣民雄鄉", "時間": "09-21 22:00", "1H雨量": "0", "累積雨量": "1", "狀態": "未達警戒"},
]

SAMPLE_FLOOD = [
    {"測站": "嘉義縣 太保市 埤鄉里埤麻腳社區", "水位": "0 公分", "狀態": "正常"},
    {"測站": "嘉義縣 朴子市 朴子市中正里", "水位": "0 公分", "狀態": "正常"},
]


def demo_records() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    now = datetime.now().isoformat(timespec="seconds")
    rain = [{**record, "抓取時間": now, "資料模式": "demo"} for record in SAMPLE_RAIN]
    flood = [{**record, "抓取時間": now, "資料模式": "demo"} for record in SAMPLE_FLOOD]
    return rain, flood


def run_demo(output_rain: Path, output_flood: Path) -> tuple[int, int]:
    rain, flood = demo_records()
    rain_count = write_csv(rain, output_rain, RAIN_FIELDNAMES)
    flood_count = write_csv(flood, output_flood, FLOOD_FIELDNAMES)
    print(f"[OK] Wrote {rain_count} rain monitor demo records to {output_rain}")
    print(f"[OK] Wrote {flood_count} flood sensor demo records to {output_flood}")
    return rain_count, flood_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect rain gauge and flood sensor data.")
    parser.add_argument("--mode", choices=["demo"], default="demo")
    parser.add_argument("--output-rain", type=Path, default=Path("data/processed/rain_monitor.csv"))
    parser.add_argument("--output-flood", type=Path, default=Path("data/processed/flood_sensors.csv"))
    args = parser.parse_args()

    run_demo(args.output_rain, args.output_flood)


if __name__ == "__main__":
    main()
