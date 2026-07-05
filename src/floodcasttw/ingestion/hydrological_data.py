"""Rain gauge and flood-sensor ingestion from WRA monitor pages."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from floodcasttw.config import get_settings
from floodcasttw.io.csv_utils import write_csv

DEFAULT_COUNTY_VALUE = "10010"
RAIN_PATH = "/monitor/rain#"
FLOOD_SENSOR_PATH = "/monitor/floodSensor#"

RAIN_FIELDNAMES = [
    "排序",
    "行政區",
    "雨量站",
    "水情時間",
    "1小時累積雨量",
    "24小時累積雨量",
    "資料產出時間",
    "抓取時間",
    "資料模式",
    "資料來源",
]
FLOOD_FIELDNAMES = [
    "排序",
    "縣市",
    "鄉鎮",
    "感測器名稱",
    "地址",
    "水情時間",
    "目前感測值",
    "資料產出時間",
    "抓取時間",
    "資料模式",
    "資料來源",
]

SAMPLE_RAIN = [
    {
        "排序": "1",
        "行政區": "嘉義縣番路鄉",
        "雨量站": "小公田(2)",
        "水情時間": "07-05 09:20",
        "1小時累積雨量": "0",
        "24小時累積雨量": "0",
    },
    {
        "排序": "2",
        "行政區": "嘉義縣民雄鄉",
        "雨量站": "民雄",
        "水情時間": "07-05 09:20",
        "1小時累積雨量": "0",
        "24小時累積雨量": "1",
    },
]

SAMPLE_FLOOD = [
    {
        "排序": "1",
        "縣市": "嘉義縣",
        "鄉鎮": "太保市",
        "感測器名稱": "埤麻腳社區",
        "地址": "嘉義縣太保市測試地址",
        "水情時間": "07-05 09:20",
        "目前感測值": "0 公分",
    },
    {
        "排序": "2",
        "縣市": "嘉義縣",
        "鄉鎮": "朴子市",
        "感測器名稱": "中正里",
        "地址": "嘉義縣朴子市測試地址",
        "水情時間": "07-05 09:20",
        "目前感測值": "0 公分",
    },
]


def demo_records() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    now = datetime.now().isoformat(timespec="seconds")
    rain = [
        {
            **record,
            "資料產出時間": "demo",
            "抓取時間": now,
            "資料模式": "demo",
            "資料來源": "demo",
        }
        for record in SAMPLE_RAIN
    ]
    flood = [
        {
            **record,
            "資料產出時間": "demo",
            "抓取時間": now,
            "資料模式": "demo",
            "資料來源": "demo",
        }
        for record in SAMPLE_FLOOD
    ]
    return rain, flood


def extract_production_time(page_text: str) -> str:
    match = re.search(r"資料產出時間：\s*([0-9:\-\s]+)", page_text)
    return match.group(1).strip() if match else ""


def parse_rain_rows(
    rows: list[list[str]],
    *,
    production_time: str,
    fetched_at: str,
    mode: str,
    source_url: str,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in rows:
        if len(row) < 6 or row[0] == "排序" or "無資料" in row:
            continue
        records.append(
            {
                "排序": row[0],
                "行政區": row[1],
                "雨量站": row[2],
                "水情時間": row[3],
                "1小時累積雨量": row[4],
                "24小時累積雨量": row[5],
                "資料產出時間": production_time,
                "抓取時間": fetched_at,
                "資料模式": mode,
                "資料來源": source_url,
            }
        )
    return records


def parse_flood_rows(
    rows: list[list[str]],
    *,
    production_time: str,
    fetched_at: str,
    mode: str,
    source_url: str,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for row in rows:
        if len(row) < 7 or row[0] == "排序" or "無資料" in row:
            continue
        records.append(
            {
                "排序": row[0],
                "縣市": row[1],
                "鄉鎮": row[2],
                "感測器名稱": row[3],
                "地址": row[4],
                "水情時間": row[5],
                "目前感測值": row[6],
                "資料產出時間": production_time,
                "抓取時間": fetched_at,
                "資料模式": mode,
                "資料來源": source_url,
            }
        )
    return records


def save_debug_capture(page, debug_dir: Path | None, label: str) -> None:
    if debug_dir is None:
        return
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{label}.html").write_text(page.content(), encoding="utf-8")
    page.screenshot(path=str(debug_dir / f"{label}.png"), full_page=True)


def write_run_summary(summary_output: Path | None, payload: dict[str, object]) -> None:
    if summary_output is None:
        return
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def table_rows(page) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in page.locator("table tr").all():
        cells = [cell.inner_text().strip() for cell in row.locator("th, td").all()]
        if cells:
            rows.append(cells)
    return rows


def scrape_live(
    *,
    county: str = DEFAULT_COUNTY_VALUE,
    headless: bool = True,
    timeout: int = 45_000,
    debug_dir: Path | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    settings = get_settings()
    rain_url = f"{settings.wra_base_url}{RAIN_PATH}"
    flood_url = f"{settings.wra_base_url}{FLOOD_SENSOR_PATH}"
    fetched_at = datetime.now().isoformat(timespec="seconds")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})

        page.goto(rain_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_selector("select#city", timeout=timeout)
        page.select_option("select#city", value=county)
        page.wait_for_timeout(2500)
        save_debug_capture(page, debug_dir, "wra_rain")
        rain_text = page.locator("body").inner_text(timeout=timeout)
        rain = parse_rain_rows(
            table_rows(page),
            production_time=extract_production_time(rain_text),
            fetched_at=fetched_at,
            mode="live",
            source_url=rain_url,
        )

        page.goto(flood_url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_selector("select#city", timeout=timeout)
        page.select_option("select#city", value=county)
        page.wait_for_timeout(2500)
        save_debug_capture(page, debug_dir, "wra_flood_sensor")
        flood_text = page.locator("body").inner_text(timeout=timeout)
        flood = parse_flood_rows(
            table_rows(page),
            production_time=extract_production_time(flood_text),
            fetched_at=fetched_at,
            mode="live",
            source_url=flood_url,
        )

        browser.close()

    return rain, flood


def run_demo(output_rain: Path, output_flood: Path) -> tuple[int, int]:
    rain, flood = demo_records()
    rain_count = write_csv(rain, output_rain, RAIN_FIELDNAMES)
    flood_count = write_csv(flood, output_flood, FLOOD_FIELDNAMES)
    print(f"[OK] Wrote {rain_count} rain monitor demo records to {output_rain}")
    print(f"[OK] Wrote {flood_count} flood sensor demo records to {output_flood}")
    return rain_count, flood_count


def run_live(
    output_rain: Path,
    output_flood: Path,
    *,
    county: str,
    headed: bool,
    timeout: int,
    debug_dir: Path | None,
    summary_output: Path | None,
) -> tuple[int, int]:
    settings = get_settings()
    rain, flood = scrape_live(
        county=county,
        headless=not headed,
        timeout=timeout,
        debug_dir=debug_dir,
    )
    rain_count = write_csv(rain, output_rain, RAIN_FIELDNAMES)
    flood_count = write_csv(flood, output_flood, FLOOD_FIELDNAMES)
    write_run_summary(
        summary_output,
        {
            "status": "ok",
            "failure_reason": "",
            "mode": "live",
            "county": county,
            "completed_at": datetime.now().isoformat(timespec="seconds"),
            "sources": {
                "rain": f"{settings.wra_base_url}{RAIN_PATH}",
                "flood_sensor": f"{settings.wra_base_url}{FLOOD_SENSOR_PATH}",
            },
            "outputs": {
                "rain": str(output_rain),
                "flood_sensor": str(output_flood),
            },
            "row_counts": {
                "rain": rain_count,
                "flood_sensor": flood_count,
            },
            "debug_dir": str(debug_dir) if debug_dir else "",
        },
    )
    print(f"[OK] Wrote {rain_count} live rain monitor records to {output_rain}")
    print(f"[OK] Wrote {flood_count} live flood sensor records to {output_flood}")
    return rain_count, flood_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect rain gauge and flood sensor data.")
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--county", default=DEFAULT_COUNTY_VALUE, help="10010 = Chiayi County")
    parser.add_argument("--output-rain", type=Path, default=Path("data/processed/rain_monitor.csv"))
    parser.add_argument(
        "--output-flood",
        type=Path,
        default=Path("data/processed/flood_sensors.csv"),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout", type=int, default=45_000)
    parser.add_argument("--debug-dir", type=Path, default=None)
    parser.add_argument("--summary-output", type=Path, default=None)
    args = parser.parse_args()

    try:
        if args.mode == "demo":
            rain_count, flood_count = run_demo(args.output_rain, args.output_flood)
            write_run_summary(
                args.summary_output,
                {
                    "status": "ok",
                    "failure_reason": "",
                    "mode": "demo",
                    "county": args.county,
                    "completed_at": datetime.now().isoformat(timespec="seconds"),
                    "sources": {"rain": "demo", "flood_sensor": "demo"},
                    "outputs": {
                        "rain": str(args.output_rain),
                        "flood_sensor": str(args.output_flood),
                    },
                    "row_counts": {"rain": rain_count, "flood_sensor": flood_count},
                    "debug_dir": "",
                },
            )
        else:
            run_live(
                args.output_rain,
                args.output_flood,
                county=args.county,
                headed=args.headed,
                timeout=args.timeout,
                debug_dir=args.debug_dir,
                summary_output=args.summary_output,
            )
    except PlaywrightTimeout as exc:
        write_run_summary(
            args.summary_output,
            {
                "status": "error",
                "failure_reason": f"Browser timeout: {exc}",
                "mode": args.mode,
                "county": args.county,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "sources": {},
                "outputs": {},
                "row_counts": {"rain": 0, "flood_sensor": 0},
                "debug_dir": str(args.debug_dir) if args.debug_dir else "",
            },
        )
        raise SystemExit(f"[ERROR] Browser timeout. Try --mode demo first. {exc}") from exc


if __name__ == "__main__":
    main()
