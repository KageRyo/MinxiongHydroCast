from minxionghydrocast.validation.normalization import (
    normalize_datetime,
    normalize_rainfall_mm,
    normalize_water_level,
)
from minxionghydrocast.validation.quality import validate_records


def test_normalize_datetime_uses_production_year_and_taipei_timezone():
    assert (
        normalize_datetime("07-05 09:20", production_time="2026-07-05 09:37")
        == "2026-07-05T09:20:00+08:00"
    )


def test_normalize_numeric_fields():
    assert normalize_rainfall_mm("12.5") == "12.5"
    assert normalize_water_level("3 公分") == ("3", "cm")
    assert normalize_water_level("--") == ("", "")


def test_validate_records_rejects_demo_in_production_mode():
    report = validate_records(
        [{"資料模式": "demo", "name": "sample"}],
        required_fields={"資料模式", "name"},
        allow_demo=False,
    )

    assert not report.ok
    assert report.errors == ["row 1: demo record cannot be used as production data"]


def test_validate_records_checks_required_non_empty_fields():
    report = validate_records(
        [{"資料模式": "live", "name": ""}],
        required_fields={"資料模式", "name"},
        required_non_empty={"name"},
        allow_demo=False,
    )

    assert not report.ok
    assert report.errors == ["row 1: empty name"]
