import hashlib
import json
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
