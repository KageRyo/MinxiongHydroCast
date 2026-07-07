from floodcasttw.ingestion.cwa_event_collector import build_event_plan


def sample_history_index():
    return {
        "data_id": "O-A0059-001",
        "files": [
            {
                "data_time": "2026-07-06T19:40:00+08:00",
                "url": "https://example.test/1940.json",
                "filename": "1940.json",
                "file_format": "JSON",
            },
            {
                "data_time": "2026-07-06T19:20:00+08:00",
                "url": "https://example.test/1920.json",
                "filename": "1920.json",
                "file_format": "JSON",
            },
            {
                "data_time": "2026-07-06T19:30:00+08:00",
                "url": "https://example.test/1930.json",
                "filename": "1930.json",
                "file_format": "JSON",
            },
        ],
    }


def test_build_event_plan_selects_sorted_frames_in_window():
    plan = build_event_plan(
        sample_history_index(),
        event_id="chiayi_20260706_evening",
        start_time="2026-07-06T19:25:00+08:00",
        end_time="2026-07-06T19:45:00+08:00",
    )

    assert plan.event_id == "chiayi_20260706_evening"
    assert plan.data_id == "O-A0059-001"
    assert plan.frame_count == 2
    assert [frame.data_time for frame in plan.frames] == [
        "2026-07-06T19:30:00+08:00",
        "2026-07-06T19:40:00+08:00",
    ]


def test_build_event_plan_applies_limit_after_sorting():
    plan = build_event_plan(
        sample_history_index(),
        event_id="limited",
        start_time="2026-07-06T19:00:00+08:00",
        end_time="2026-07-06T20:00:00+08:00",
        limit=2,
    )

    assert plan.frame_count == 2
    assert [frame.filename for frame in plan.frames] == ["1920.json", "1930.json"]


def test_build_event_plan_rejects_reversed_time_window():
    try:
        build_event_plan(
            sample_history_index(),
            event_id="bad",
            start_time="2026-07-06T20:00:00+08:00",
            end_time="2026-07-06T19:00:00+08:00",
        )
    except ValueError as exc:
        assert "end_time" in str(exc)
    else:
        raise AssertionError("expected reversed window to fail")
