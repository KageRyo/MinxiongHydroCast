import json
from pathlib import Path

from floodcasttw.models.event_splits import EventSplitManifest, WeatherEvent, load_manifest


def test_sample_event_split_manifest_is_ok():
    manifest = load_manifest(Path("data/samples/event_split_manifest.json"))
    result = manifest.check()

    assert result["status"] == "ok"
    assert result["split_strategy"] == "event_based"
    assert result["split_counts"] == {"train": 2, "validation": 3, "test": 3}
    assert any(
        event["event_id"] == "cwa_o_a0059_recent_sample_20260707"
        for event in result["events"]
    )
    assert result["errors"] == []


def test_radar_event_windows_are_registered_in_event_splits():
    manifest = load_manifest(Path("data/samples/event_split_manifest.json"))
    event_ids = {event.event_id for event in manifest.events}
    radar_windows = json.loads(
        Path("data/samples/radar_event_windows.json").read_text(encoding="utf-8")
    )

    candidate_ids = {
        candidate["event_id"] for candidate in radar_windows["candidate_windows"]
    }

    assert candidate_ids
    assert candidate_ids <= event_ids


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
