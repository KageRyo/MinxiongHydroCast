"""Normalization helpers for WRA-style timestamps and numeric fields."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
NUMBER_PATTERN = re.compile(r"[-+]?\d+(?:\.\d+)?")


def now_taipei_iso() -> str:
    return datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")


def infer_year(value: str | None) -> int:
    if value:
        match = re.search(r"\b(20\d{2}|19\d{2})\b", value)
        if match:
            return int(match.group(1))
    return datetime.now(TAIPEI_TZ).year


def normalize_datetime(
    value: str,
    *,
    production_time: str | None = None,
    timezone: ZoneInfo = TAIPEI_TZ,
) -> str:
    text = value.strip()
    if not text or text == "demo":
        return ""

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone)
        return parsed.astimezone(timezone).isoformat(timespec="seconds")
    except ValueError:
        pass

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text, pattern).replace(tzinfo=timezone)
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            pass

    inferred_year = infer_year(production_time)
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(f"{inferred_year}-{text}", pattern).replace(tzinfo=timezone)
            return parsed.isoformat(timespec="seconds")
        except ValueError:
            pass

    return ""


def numeric_text(value: str) -> str:
    match = NUMBER_PATTERN.search(value.replace(",", ""))
    return match.group(0) if match else ""


def normalize_rainfall_mm(value: str) -> str:
    return numeric_text(value)


def normalize_water_level(value: str) -> tuple[str, str]:
    text = value.strip()
    number = numeric_text(text)
    if not number:
        return "", ""
    if "公分" in text or "cm" in text.lower():
        return number, "cm"
    if "毫米" in text or "mm" in text.lower():
        return number, "mm"
    if "公尺" in text or "m" in text.lower():
        return number, "m"
    return number, ""
