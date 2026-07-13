"""WRA rainfall alert scraper for county-level alert thresholds."""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from minxionghydrocast.config import get_settings
from minxionghydrocast.io.csv_utils import write_csv
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
    now_taipei_iso,
)
from minxionghydrocast.validation.quality import ValidationReport, validate_records

DEFAULT_COUNTY_VALUE = "10010"
DEFAULT_OUTPUT = Path("data/processed/rainfall_alerts.csv")
PIPELINE_NAME = "rainfall_alerts"
FIELDNAMES = [
    "雨量站代碼",
    "縣市代碼",
    "鄉鎮代碼",
    "地區",
    "水情時間",
    "水情時間ISO",
    "警戒",
    "警戒級別",
    "影響村落",
    "10分鐘雨量mm",
    "1小時雨量mm",
    "3小時雨量mm",
    "6小時雨量mm",
    "12小時雨量mm",
    "24小時雨量mm",
    "抓取時間",
    "資料模式",
    "資料來源",
]
NON_EMPTY_FIELDS = {"地區", "警戒", "抓取時間", "資料模式"}

SAMPLE_DATA = [
    {
        "雨量站代碼": "demo-minxiong",
        "縣市代碼": "10010",
        "鄉鎮代碼": "10010050",
        "地區": "嘉義 民雄鄉",
        "水情時間": "",
        "水情時間ISO": "",
        "警戒": "未達警戒",
        "警戒級別": "0",
        "影響村落": "民雄鄉-雙福村,福樂村,大崎村,秀林村,金興村,北斗村",
        "10分鐘雨量mm": "0",
        "1小時雨量mm": "0",
        "3小時雨量mm": "0",
        "6小時雨量mm": "0",
        "12小時雨量mm": "0",
        "24小時雨量mm": "0",
        "資料來源": "demo",
    },
    {
        "雨量站代碼": "demo-shakeng",
        "縣市代碼": "10010",
        "鄉鎮代碼": "",
        "地區": "沙坑 竹崎鄉",
        "水情時間": "",
        "水情時間ISO": "",
        "警戒": "未達警戒",
        "警戒級別": "0",
        "影響村落": "竹崎鄉-灣橋村,沙坑村,獅埜村,龍山村",
        "10分鐘雨量mm": "0",
        "1小時雨量mm": "0",
        "3小時雨量mm": "0",
        "6小時雨量mm": "0",
        "12小時雨量mm": "0",
        "24小時雨量mm": "0",
        "資料來源": "demo",
    },
]


def demo_records() -> list[dict[str, str]]:
    now = now_taipei_iso()
    return [{**record, "抓取時間": now, "資料模式": "demo"} for record in SAMPLE_DATA]


def validate_rainfall_alert_records(
    records: list[dict[str, str]],
    *,
    allow_demo: bool,
) -> ValidationReport:
    return validate_records(
        records,
        required_fields=set(FIELDNAMES),
        required_non_empty=NON_EMPTY_FIELDS,
        allow_demo=allow_demo,
    )


def scrape_with_playwright(
    county_value: str = DEFAULT_COUNTY_VALUE,
    headless: bool = True,
    timeout: int = 45_000,
) -> list[dict[str, str]]:
    settings = get_settings()
    url = f"{settings.wra_base_url}/service/alertQuery#"
    records: list[dict[str, str]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        page.wait_for_timeout(2500)

        selected = False
        for selector in (
            "#ra_city",
            "#city",
            "select[id*='city']",
            "select[id*='county']",
            "select[name*='city']",
        ):
            try:
                page.wait_for_selector(selector, timeout=4000)
                page.select_option(selector, value=county_value)
                selected = True
                break
            except Exception:
                continue

        if not selected:
            print("[WARN] County selector not found; attempting to parse visible page content.")

        page.wait_for_timeout(3000)
        now = now_taipei_iso()

        for header in page.locator("h4").all()[:120]:
            try:
                location = header.inner_text().strip().replace("[", "").replace("]", "")
                if not location or len(location) < 2:
                    continue

                parent = header.locator("xpath=ancestor::div[1]")
                status = "未知"
                affected = ""
                rain_1h = ""
                rain_3h = ""
                rain_6h = ""

                status_el = parent.locator("text=/未達警戒|警戒中|發布|解除/").first
                if status_el.count() > 0:
                    status = status_el.inner_text().strip()[:20]

                affected_el = parent.locator("text=/影響範圍/").first
                if affected_el.count() > 0:
                    affected = affected_el.inner_text().replace("影響範圍:", "").strip()

                for table in parent.locator("table").all():
                    tokens = [
                        part.strip()
                        for part in table.inner_text().replace("\n", " ").split()
                    ]
                    for index, token in enumerate(tokens):
                        upper = token.upper()
                        if upper == "1H":
                            rain_1h = " ".join(tokens[index : index + 4])
                        elif upper == "3H":
                            rain_3h = " ".join(tokens[index : index + 4])
                        elif upper == "6H":
                            rain_6h = " ".join(tokens[index : index + 4])

                records.append(
                    {
                        "雨量站代碼": "",
                        "縣市代碼": county_value,
                        "鄉鎮代碼": "",
                        "地區": location,
                        "水情時間": "",
                        "水情時間ISO": "",
                        "警戒": status,
                        "警戒級別": "",
                        "影響村落": affected,
                        "10分鐘雨量mm": "",
                        "1小時雨量mm": _current_rainfall(rain_1h),
                        "3小時雨量mm": _current_rainfall(rain_3h),
                        "6小時雨量mm": _current_rainfall(rain_6h),
                        "12小時雨量mm": "",
                        "24小時雨量mm": "",
                        "抓取時間": now,
                        "資料模式": "live",
                        "資料來源": url,
                    }
                )
            except Exception as exc:
                print(f"[DEBUG] Skipped alert card: {exc}")

        browser.close()

    return records


def _current_rainfall(value: str) -> str:
    """Extract the current value from the page's `1H current level1 level2` text."""

    parts = value.split()
    if len(parts) < 2:
        return ""
    try:
        return f"{float(parts[1]):g}"
    except ValueError:
        return ""


def run(output: Path, mode: str, county: str, headed: bool, timeout: int) -> int:
    if mode == "demo":
        records = demo_records()
    else:
        records = scrape_with_playwright(county_value=county, headless=not headed, timeout=timeout)
        if not records:
            raise RuntimeError("No rainfall alert records were extracted from the live page.")

    count = write_csv(records, output, FIELDNAMES)
    print(f"[OK] Wrote {count} rainfall alert records to {output}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect WRA rainfall alert data.")
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument("--county", default=DEFAULT_COUNTY_VALUE, help="10010 = Chiayi County")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--timeout", type=int, default=45_000)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    try:
        count = run(args.output, args.mode, args.county, args.headed, args.timeout)
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="ok",
            started_at=started_at,
            start_timer=start_timer,
            mode=args.mode,
            inputs={"county": args.county},
            outputs={"rainfall_alerts": str(args.output)},
            row_counts={"rainfall_alerts": count},
            metadata={"headed": args.headed, "timeout_ms": args.timeout},
        )
        record_run(
            summary_output=args.summary_output,
            log_output=args.log_output,
            summary=summary,
        )
    except PlaywrightTimeout as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=f"Browser timeout: {exc}",
            started_at=started_at,
            start_timer=start_timer,
            mode=args.mode,
            inputs={"county": args.county},
            outputs={"rainfall_alerts": str(args.output)},
            row_counts={"rainfall_alerts": 0},
            metadata={"headed": args.headed, "timeout_ms": args.timeout},
        )
        record_run(
            summary_output=args.summary_output,
            log_output=args.log_output,
            summary=summary,
        )
        raise SystemExit(f"[ERROR] Browser timeout. Try --mode demo first. {exc}") from exc
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=str(exc),
            started_at=started_at,
            start_timer=start_timer,
            mode=args.mode,
            inputs={"county": args.county},
            outputs={"rainfall_alerts": str(args.output)},
            row_counts={"rainfall_alerts": 0},
            metadata={"headed": args.headed, "timeout_ms": args.timeout},
        )
        record_run(
            summary_output=args.summary_output,
            log_output=args.log_output,
            summary=summary,
        )
        raise


if __name__ == "__main__":
    main()
