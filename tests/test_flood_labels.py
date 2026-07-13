from minxionghydrocast.validation.flood_labels import LabelCriteria, audit_labels


def label(event_id, start, end, observed_flood):
    return {
        "event_id": event_id,
        "township": "民雄鄉",
        "start_at": start,
        "end_at": end,
        "observed_flood": observed_flood,
        "source_type": "official_report",
        "source_reference": f"official:{event_id}",
        "reviewed_by": "operator@example.test",
        "reviewed_at": "2026-07-11T10:00:00+08:00",
        "confirmed": True,
    }


def test_label_audit_requires_confirmed_positive_and_negative_events():
    labels = [
        label(
            "positive",
            "2026-07-01T00:00:00+08:00",
            "2026-07-01T03:00:00+08:00",
            True,
        ),
        label(
            "negative",
            "2026-07-02T00:00:00+08:00",
            "2026-07-02T03:00:00+08:00",
            False,
        ),
    ]

    report = audit_labels(
        labels,
        criteria=LabelCriteria(minimum_positive_events=1, minimum_negative_events=1),
    )

    assert report["errors"] == []
    assert report["counts"] == {
        "submitted": 2,
        "confirmed": 2,
        "positive": 1,
        "negative": 1,
    }
    assert report["training_ready"] is True


def test_label_audit_rejects_unconfirmed_non_minxiong_and_overlapping_events():
    first = label(
        "first",
        "2026-07-01T00:00:00+08:00",
        "2026-07-01T03:00:00+08:00",
        True,
    )
    second = label(
        "second",
        "2026-07-01T02:00:00+08:00",
        "2026-07-01T04:00:00+08:00",
        False,
    )
    second["township"] = "太保市"
    second["confirmed"] = False

    report = audit_labels(
        [first, second],
        criteria=LabelCriteria(minimum_positive_events=1, minimum_negative_events=1),
    )

    assert "label 2: township must be 民雄鄉" in report["errors"]
    assert "label 2: confirmed must be true" in report["errors"]
    assert report["training_ready"] is False
