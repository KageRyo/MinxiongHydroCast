import json
from pathlib import Path

from floodcasttw.models.event_splits import EventSplitManifest, WeatherEvent, load_manifest


def test_sample_event_split_manifest_is_ok():
    manifest = load_manifest(Path("data/samples/event_split_manifest.json"))
    result = manifest.check()

    assert result["status"] == "ok"
    assert result["split_strategy"] == "event_based"
    assert result["split_counts"] == {"train": 3, "validation": 2, "test": 3}
    assert any(
        event["event_id"] == "cwa_o_a0059_recent_sample_20260707"
        for event in result["events"]
    )
    assert result["errors"] == []


def test_radar_event_windows_are_registered_in_event_splits():
    manifest = load_manifest(Path("data/samples/event_split_manifest.json"))
    event_ids = {event.event_id for event in manifest.events}
    split_by_event_id = {
        event_id: split_name
        for split_name, split_event_ids in manifest.splits.items()
        for event_id in split_event_ids
    }
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )

    candidate_ids = {
        candidate["event_id"] for candidate in radar_windows["candidate_windows"]
    }

    assert candidate_ids
    assert candidate_ids <= event_ids
    for candidate in radar_windows["candidate_windows"]:
        assert split_by_event_id[candidate["event_id"]] == candidate["model_split"]
        assert candidate["collection_status"] == "full_sequence_collected_locally_ignored"
        assert candidate["tensor_status"] == "sliding_window_tensor_collected_locally_ignored"


def test_radar_event_windows_have_weather_context_entries():
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )
    weather_context = json.loads(
        Path("data/samples/event_weather_context.json").read_text(encoding="utf-8")
    )
    allowed_weather_types = set(weather_context["allowed_weather_types"])
    context_by_event_id = {event["event_id"]: event for event in weather_context["events"]}

    for candidate in radar_windows["candidate_windows"]:
        context = context_by_event_id[candidate["event_id"]]
        assert context["official_weather_type"] in allowed_weather_types
        assert context["status"] in {"needs_official_source", "officially_labeled"}
        if context["status"] == "needs_official_source":
            assert context["official_weather_type"] == "official_context_pending"
            assert context["official_evidence"] == []


def test_weather_context_source_review_covers_pending_radar_windows():
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )
    weather_context = json.loads(
        Path("data/samples/event_weather_context.json").read_text(encoding="utf-8")
    )
    source_review = json.loads(
        Path("data/samples/weather_context_source_review.json").read_text(encoding="utf-8")
    )
    candidate_ids = {
        candidate["event_id"] for candidate in radar_windows["candidate_windows"]
    }
    review_by_event_id = {event["event_id"]: event for event in source_review["events"]}

    assert weather_context["source_review"] == "data/samples/weather_context_source_review.json"
    assert candidate_ids <= set(review_by_event_id)
    for source in source_review["official_sources_reviewed"]:
        assert source["provider"] == "Central Weather Administration"
        assert source["url"].startswith(("https://www.cwa.gov.tw/", "https://opendata.cwa.gov.tw/"))
    for event_id in candidate_ids:
        event = review_by_event_id[event_id]
        assert event["official_weather_type"] == "official_context_pending"
        assert event["label_status"].startswith("blocked_")
        assert event["needed_sources"]
        assert all("Authorization=" not in url for url in event["next_probe_urls"])


def test_event_expansion_queue_tracks_uncollected_candidates_only():
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )
    expansion_queue = json.loads(
        Path("data/samples/event_expansion_queue.json").read_text(encoding="utf-8")
    )
    collected_event_ids = {
        candidate["event_id"] for candidate in radar_windows["candidate_windows"]
    }
    queued = expansion_queue["candidates"]
    queued_event_ids = {candidate["event_id"] for candidate in queued}

    assert collected_event_ids.isdisjoint(queued_event_ids)
    assert len(queued) >= 5
    assert any(
        candidate["candidate_family"] == "chiayi_minxiong_local_heavy_rain"
        for candidate in queued
    )
    assert any(
        candidate["candidate_family"] == "taiwan_wide_front_or_meiyu"
        for candidate in queued
    )
    for candidate in queued:
        required = set(candidate["required_before_training"])
        assert "attach official CWA weather context" in required
        assert "run O-B0045-001 QPE versus O-A0002-001 gauge validation" in required


def test_qpe_gauge_validation_status_covers_radar_event_windows():
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )
    validation_status = json.loads(
        Path("data/samples/qpe_gauge_validation_status.json").read_text(encoding="utf-8")
    )
    candidate_ids = {
        candidate["event_id"] for candidate in radar_windows["candidate_windows"]
    }
    status_by_event_id = {event["event_id"]: event for event in validation_status["events"]}

    assert candidate_ids <= set(status_by_event_id)
    assert validation_status["required_products"]["qpe"]["data_id"] == "O-B0045-001"
    assert validation_status["required_products"]["gauge"]["data_id"] == "O-A0002-001"
    for event_id in candidate_ids:
        event = status_by_event_id[event_id]
        assert event["gauge_status"] == "fetched_locally_ignored_parse_verified"
        assert event["gauge_format"] in {"json", "xml"}
        assert event["gauge_station_count"] > 0
        assert event["qpe_redacted_endpoint"].endswith("Authorization=REDACTED")
        if event["qpe_status"].startswith("blocked_"):
            assert event["report_status"] == "blocked_missing_event_time_qpe_grid"
            assert event["qpe_probe_summary"].startswith("data/processed/run_summaries/")


def test_weather_event_rejects_invalid_time_order():
    event = WeatherEvent(
        event_id="bad_time",
        name="Bad time",
        event_type="extreme_rainfall",
        region="Chiayi County",
        start_time="2025-08-13T00:00:00+08:00",
        end_time="2025-08-12T00:00:00+08:00",
    )

    assert "bad_time: end_time must be after start_time" in event.validation_errors()


def test_manifest_rejects_event_leakage_between_splits():
    manifest = EventSplitManifest(
        schema_version="1.0",
        split_strategy="event_based",
        target="radar_nowcasting",
        events=(
            WeatherEvent(
                event_id="same_storm",
                name="Same storm",
                event_type="typhoon",
                region="Taiwan",
                start_time="2025-07-01T00:00:00+08:00",
                end_time="2025-07-02T00:00:00+08:00",
            ),
        ),
        splits={
            "train": ("same_storm",),
            "validation": ("same_storm",),
            "test": ("same_storm",),
        },
    )

    result = manifest.check()

    assert result["status"] == "error"
    assert any(
        "same_storm appears in both train and validation" in error
        for error in result["errors"]
    )


def test_manifest_rejects_unknown_split_reference(tmp_path: Path):
    manifest_path = tmp_path / "event_split_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "split_strategy": "event_based",
                "target": "radar_nowcasting",
                "events": [
                    {
                        "event_id": "known_event",
                        "name": "Known event",
                        "event_type": "meiyu_front",
                        "region": "Taiwan",
                        "start_time": "2025-06-01T00:00:00+08:00",
                        "end_time": "2025-06-02T00:00:00+08:00",
                    }
                ],
                "splits": {
                    "train": ["known_event"],
                    "validation": ["missing_event"],
                    "test": ["known_event"],
                },
            }
        ),
        encoding="utf-8",
    )

    result = load_manifest(manifest_path).check()

    assert "validation references unknown event_id: missing_event" in result["errors"]
