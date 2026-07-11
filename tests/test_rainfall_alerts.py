from floodcastminxiong.ingestion.rainfall_alerts import (
    demo_records,
    validate_rainfall_alert_records,
)


def test_rainfall_alert_validation_accepts_demo_only_when_explicitly_allowed():
    records = demo_records()

    assert validate_rainfall_alert_records(records, allow_demo=True).ok
    production_report = validate_rainfall_alert_records(records, allow_demo=False)
    assert not production_report.ok
    assert production_report.errors == [
        "row 1: demo record cannot be used as production data",
        "row 2: demo record cannot be used as production data",
    ]
