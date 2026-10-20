import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from scripts.validate_public_contracts import validate_public_manifest


def write_manifest_and_checksum(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, Path]:
    manifest_path = tmp_path / "event_split_manifest.json"
    manifest_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    checksum_path = tmp_path / "event_split_manifest.json.sha256"
    checksum_path.write_text(
        f"{hashlib.sha256(manifest_path.read_bytes()).hexdigest()}  {manifest_path.name}\n",
        encoding="utf-8",
    )
    return manifest_path, checksum_path


def valid_manifest_payload() -> dict[str, object]:
    events = []
    splits = {"train": [], "validation": [], "test": []}
    definitions = [
        ("train_one", "train", "Taiwan"),
        ("train_two", "train", "Taiwan"),
        ("validation_one", "validation", "Chiayi County"),
        ("test_one", "test", "Minxiong, Chiayi County"),
        ("test_two", "test", "Minxiong, Chiayi County"),
    ]
    for index, (event_id, split, region) in enumerate(definitions, start=6):
        events.append(
            {
                "event_id": event_id,
                "name": event_id,
                "event_type": "radar_candidate",
                "region": region,
                "start_time": f"2026-07-{index:02d}T12:00:00+08:00",
                "end_time": f"2026-07-{index:02d}T14:00:00+08:00",
                "source": "CWA historyAPI O-A0059-001",
            }
        )
        splits[split].append(event_id)
    return {
        "schema_version": "2.0",
        "split_strategy": "event_based",
        "target": "radar_nowcasting",
        "dataset": {
            "data_id": "O-A0059-001",
            "source_format": "cwa_opendata_grid",
            "input_length": 2,
            "prediction_length": 2,
            "cadence_minutes": 10,
            "units": "dBZ",
            "crs": "TWD67",
            "window_stride_frames": 1,
            "event_threshold": 35.0,
            "minimum_counts": {
                "train": 2,
                "validation": 1,
                "test": 2,
                "minxiong_test": 2,
            },
        },
        "events": events,
        "splits": splits,
    }


def test_public_manifest_validates_with_matching_checksum(tmp_path: Path):
    manifest_path, checksum_path = write_manifest_and_checksum(
        tmp_path, valid_manifest_payload()
    )

    manifest = validate_public_manifest(
        manifest_path=manifest_path,
        checksum_path=checksum_path,
    )

    assert manifest.schema_version == "2.0"
    assert len(manifest.events) == 5


def test_public_manifest_rejects_checksum_drift(tmp_path: Path):
    manifest_path, checksum_path = write_manifest_and_checksum(
        tmp_path, valid_manifest_payload()
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["target"] = "changed_target"
    manifest_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="manifest checksum mismatch"):
        validate_public_manifest(
            manifest_path=manifest_path,
            checksum_path=checksum_path,
        )


def test_public_manifest_rejects_schema_drift(tmp_path: Path):
    payload = valid_manifest_payload()
    payload["unexpected_field"] = True
    manifest_path, checksum_path = write_manifest_and_checksum(tmp_path, payload)

    with pytest.raises(ValueError, match="manifest schema validation failed"):
        validate_public_manifest(
            manifest_path=manifest_path,
            checksum_path=checksum_path,
        )


def test_formal_events_have_explicit_evidence_status():
    """Missing evidence must remain visible for every current formal event."""
    manifest = validate_public_manifest()
    for name in ("event_weather_context.json", "qpe_gauge_validation_status.json"):
        payload = json.loads((Path("data/samples") / name).read_text())
        by_id = {event["event_id"]: event for event in payload["events"]}
        assert all(event.event_id in by_id for event in manifest.events)


def test_public_frame_inventory_matches_fixed_split_and_checksum():
    """CI checks the published metadata without needing official raw files."""
    manifest = validate_public_manifest()
    path = Path("data/samples/formal_event_inventory.json")
    checksum = path.with_suffix(".json.sha256").read_text().split()
    assert checksum == [hashlib.sha256(path.read_bytes()).hexdigest(), path.name]
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == "1.0"
    assert payload["dataset_release_ready"] is False
    assert payload["forecast_publication_ready"] is False
    assert payload["split_manifest_sha256"] == hashlib.sha256(
        Path("data/samples/event_split_manifest.json").read_bytes()
    ).hexdigest()
    events = payload["events"]
    assert [event["event_id"] for event in events] == [e.event_id for e in manifest.events]
    for event, formal in zip(events, manifest.events):
        assert event["split"] == manifest.split_for(formal.event_id)
        assert event["weather_context_status"] == "official_context_pending"
        assert event["human_review_status"] == "pending"
        assert event["source_data_id"] == manifest.dataset.data_id
        start = datetime.fromisoformat(formal.start_time)
        end = datetime.fromisoformat(formal.end_time)
        step = timedelta(minutes=manifest.dataset.cadence_minutes)
        frames = event["frames"]
        assert len(frames) == (end - start) // step + 1
        assert event["expected_frame_count"] == event["verified_frame_count"] == len(frames)
        assert event["grid"]["crs"] == manifest.dataset.crs
        assert event["grid"]["units"] == manifest.dataset.units
        assert event["grid"]["bounds_kind"] == "outermost_grid_point_centers"
        assert len(event["grid"]["bbox"]) == 4
        for index, frame in enumerate(frames):
            assert set(frame) == {"data_time", "bytes", "sha256", "source_url"}
            assert datetime.fromisoformat(frame["data_time"]) == start + index * step
            assert type(frame["bytes"]) is int and frame["bytes"] > 0
            assert len(frame["sha256"]) == 64
            assert all(c in "0123456789abcdef" for c in frame["sha256"])
            assert frame["source_url"].startswith(
                "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/history/Observation/"
            )
            assert "?" not in frame["source_url"]
