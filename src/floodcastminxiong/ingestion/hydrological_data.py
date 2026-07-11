"""Rain gauge and flood-sensor ingestion from WRA monitor pages."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from floodcastminxiong.config import get_settings
from floodcastminxiong.io.csv_utils import write_csv
from floodcastminxiong.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcastminxiong.validation.normalization import (
    normalize_datetime,
    normalize_rainfall_mm,
    normalize_water_level,
    now_taipei_iso,
)
from floodcastminxiong.validation.quality import ValidationReport, validate_records
from floodcastminxiong.validation.schemas import (
    FLOOD_SENSOR_REQUIRED_FIELDS,
    RAIN_GAUGE_REQUIRED_FIELDS,
)

DEFAULT_COUNTY_VALUE = "10010"
RAIN_PATH = "/monitor/rain#"
FLOOD_SENSOR_PATH = "/monitor/floodSensor#"
PIPELINE_NAME = "hydrology"

RAIN_FIELDNAMES = [
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
]
FLOOD_FIELDNAMES = [
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
]

RAIN_NON_EMPTY_FIELDS = {
    "行政區",
    "雨量站",
    "水情時間ISO",
    "資料模式",
    "資料來源",
}
FLOOD_NON_EMPTY_FIELDS = {
    "縣市",
    "鄉鎮",
    "感測器名稱",
    "水情時間ISO",
    "資料模式",
    "資料來源",
}

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
    now = now_taipei_iso()
    production_time = "2026-07-05 09:42"
    rain = [
        {
            **record,
            "雨量站代碼": "",
            "水情時間ISO": normalize_datetime(
                record["水情時間"],
                production_time=production_time,
            ),
            "1小時累積雨量mm": normalize_rainfall_mm(record["1小時累積雨量"]),
            "24小時累積雨量mm": normalize_rainfall_mm(record["24小時累積雨量"]),
            "緯度": "",
            "經度": "",
            "資料產出時間": production_time,
            "資料產出時間ISO": normalize_datetime(production_time),
            "抓取時間": now,
            "資料模式": "demo",
            "資料來源": "demo",
        }
        for record in SAMPLE_RAIN
    ]
    flood = [
        {
            **record,
            "水情時間ISO": normalize_datetime(
                record["水情時間"],
                production_time=production_time,
            ),
            "目前感測值數值": normalize_water_level(record["目前感測值"])[0],
            "目前感測值單位": normalize_water_level(record["目前感測值"])[1],
            "資料產出時間": production_time,
            "資料產出時間ISO": normalize_datetime(production_time),
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
    production_time_iso = normalize_datetime(production_time)
    for row in rows:
        if len(row) < 6 or row[0] == "排序" or "無資料" in row:
            continue
        records.append(
            {
                "排序": row[0],
                "行政區": row[1],
                "雨量站": row[2],
                "雨量站代碼": "",
                "水情時間": row[3],
                "水情時間ISO": normalize_datetime(row[3], production_time=production_time),
                "1小時累積雨量": row[4],
                "1小時累積雨量mm": normalize_rainfall_mm(row[4]),
                "24小時累積雨量": row[5],
                "24小時累積雨量mm": normalize_rainfall_mm(row[5]),
                "緯度": "",
                "經度": "",
                "資料產出時間": production_time,
                "資料產出時間ISO": production_time_iso,
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
    production_time_iso = normalize_datetime(production_time)
    for row in rows:
        if len(row) < 7 or row[0] == "排序" or "無資料" in row:
            continue
        water_level_value, water_level_unit = normalize_water_level(row[6])
        records.append(
            {
                "排序": row[0],
                "縣市": row[1],
                "鄉鎮": row[2],
                "感測器名稱": row[3],
                "地址": row[4],
                "水情時間": row[5],
                "水情時間ISO": normalize_datetime(row[5], production_time=production_time),
                "目前感測值": row[6],
                "目前感測值數值": water_level_value,
                "目前感測值單位": water_level_unit,
                "資料產出時間": production_time,
                "資料產出時間ISO": production_time_iso,
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


def report_payload(report: ValidationReport) -> dict[str, object]:
    return {"ok": report.ok, "row_count": report.row_count, "errors": report.errors}


def build_hydrology_summary(
    *,
    status: str,
    failure_reason: str,
    mode: str,
    county: str,
    output_rain: Path,
    output_flood: Path,
    rain_count: int,
    flood_count: int,
    started_at: str,
    start_timer: float,
    debug_dir: Path | None = None,
    rain_report: ValidationReport | None = None,
    flood_report: ValidationReport | None = None,
) -> dict[str, object]:
    settings = get_settings()
    validation = {}
    if rain_report and flood_report:
        validation = {
            "rain": report_payload(rain_report),
            "flood_sensor": report_payload(flood_report),
        }
    return build_run_summary(
        pipeline=PIPELINE_NAME,
        status=status,
        failure_reason=failure_reason,
        started_at=started_at,
        start_timer=start_timer,
        mode=mode,
        inputs={"county": county},
        outputs={
            "rain": str(output_rain),
            "flood_sensor": str(output_flood),
        },
        row_counts={"rain": rain_count, "flood_sensor": flood_count},
        validation=validation,
        metadata={
            "sources": {
                "rain": f"{settings.wra_base_url}{RAIN_PATH}" if mode == "live" else "demo",
                "flood_sensor": (
                    f"{settings.wra_base_url}{FLOOD_SENSOR_PATH}" if mode == "live" else "demo"
                ),
            },
            "debug_dir": str(debug_dir) if debug_dir else "",
        },
    )


def validate_hydrology_records(
    rain: list[dict[str, str]],
    flood: list[dict[str, str]],
    *,
    allow_demo: bool,
) -> tuple[ValidationReport, ValidationReport]:
    rain_report = validate_records(
        rain,
        required_fields=RAIN_GAUGE_REQUIRED_FIELDS,
        required_non_empty=RAIN_NON_EMPTY_FIELDS,
        allow_demo=allow_demo,
    )
    flood_report = validate_records(
        flood,
        required_fields=FLOOD_SENSOR_REQUIRED_FIELDS,
        required_non_empty=FLOOD_NON_EMPTY_FIELDS,
        allow_demo=allow_demo,
    )
    return rain_report, flood_report


def raise_if_invalid(*reports: ValidationReport) -> None:
    errors = [error for report in reports for error in report.errors]
    if errors:
        raise ValueError("; ".join(errors))


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
    fetched_at = now_taipei_iso()

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


def scrape_flood_live(
    *,
    county: str = DEFAULT_COUNTY_VALUE,
    headless: bool = True,
    timeout: int = 45_000,
    debug_dir: Path | None = None,
) -> list[dict[str, str]]:
    """Collect only the WRA flood-sensor page when rain comes from the CWA API."""

    settings = get_settings()
    flood_url = f"{settings.wra_base_url}{FLOOD_SENSOR_PATH}"
    fetched_at = now_taipei_iso()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=headless)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
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
    return flood


def run_demo(output_rain: Path, output_flood: Path) -> tuple[int, int]:
    rain, flood = demo_records()
    rain_report, flood_report = validate_hydrology_records(rain, flood, allow_demo=True)
    raise_if_invalid(rain_report, flood_report)
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
    log_output: Path | None = None,
    started_at: str | None = None,
    start_timer: float | None = None,
) -> tuple[int, int]:
    if started_at is None or start_timer is None:
        started_at, start_timer = start_run()
    rain, flood = scrape_live(
        county=county,
        headless=not headed,
        timeout=timeout,
        debug_dir=debug_dir,
    )
    rain_report, flood_report = validate_hydrology_records(rain, flood, allow_demo=False)
    if not rain_report.ok or not flood_report.ok:
        summary = build_hydrology_summary(
            status="error",
            failure_reason="validation failed",
            mode="live",
            county=county,
            output_rain=output_rain,
            output_flood=output_flood,
            rain_count=rain_report.row_count,
            flood_count=flood_report.row_count,
            started_at=started_at,
            start_timer=start_timer,
            debug_dir=debug_dir,
            rain_report=rain_report,
            flood_report=flood_report,
        )
        record_run(summary_output=summary_output, log_output=log_output, summary=summary)
        raise_if_invalid(rain_report, flood_report)

    rain_count = write_csv(rain, output_rain, RAIN_FIELDNAMES)
    flood_count = write_csv(flood, output_flood, FLOOD_FIELDNAMES)
    summary = build_hydrology_summary(
        status="ok",
        failure_reason="",
        mode="live",
        county=county,
        output_rain=output_rain,
        output_flood=output_flood,
        rain_count=rain_count,
        flood_count=flood_count,
        started_at=started_at,
        start_timer=start_timer,
        debug_dir=debug_dir,
        rain_report=rain_report,
        flood_report=flood_report,
    )
    record_run(summary_output=summary_output, log_output=log_output, summary=summary)
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
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    try:
        if args.mode == "demo":
            rain_count, flood_count = run_demo(args.output_rain, args.output_flood)
            summary = build_hydrology_summary(
                status="ok",
                failure_reason="",
                mode="demo",
                county=args.county,
                output_rain=args.output_rain,
                output_flood=args.output_flood,
                rain_count=rain_count,
                flood_count=flood_count,
                started_at=started_at,
                start_timer=start_timer,
            )
            record_run(
                summary_output=args.summary_output,
                log_output=args.log_output,
                summary=summary,
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
                log_output=args.log_output,
                started_at=started_at,
                start_timer=start_timer,
            )
    except PlaywrightTimeout as exc:
        summary = build_hydrology_summary(
            status="error",
            failure_reason=f"Browser timeout: {exc}",
            mode=args.mode,
            county=args.county,
            output_rain=args.output_rain,
            output_flood=args.output_flood,
            rain_count=0,
            flood_count=0,
            started_at=started_at,
            start_timer=start_timer,
            debug_dir=args.debug_dir,
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        raise SystemExit(f"[ERROR] Browser timeout. Try --mode demo first. {exc}") from exc


if __name__ == "__main__":
    main()
