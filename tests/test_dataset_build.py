import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from minxionghydrocast.models.radar_tensor import RadarTensorSpec
from minxionghydrocast.models.dataset_schemas import EventModelComparison
from minxionghydrocast.pipelines.dataset_build import (
    ArtifactRecord,
    DatasetVerificationReport,
    ResearchLayout,
    artifact_record,
    combine_split_archives,
    expected_frame_count,
    load_dataset_manifest,
    promotion_gate_failures,
    require_external_research_root,
    resolve_catalog_artifact_path,
)
from minxionghydrocast.pipelines.radar_tensor_conversion import (
    load_tensor_archive,
    write_tensor_archive,
)


def manifest_payload() -> dict[str, object]:
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
                "name": event_id.replace("_", " "),
                "event_type": "radar_candidate",
                "region": region,
                "start_time": f"2026-07-{index:02d}T12:00:00+08:00",
                "end_time": f"2026-07-{index:02d}T14:00:00+08:00",
                "source": "CWA historyAPI O-A0059-001",
                "notes": "",
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
        "notes": [],
    }


def write_manifest(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def model_comparison(
    event_id: str,
    split: str,
    *,
    tiny_rmse: float = 8.0,
    tiny_csi: float = 0.3,
) -> EventModelComparison:
    def lead(rmse: float, csi: float) -> dict[str, object]:
        return {
            "lead_index": 0,
            "lead_time_minutes": 10,
            "rmse": rmse,
            "event_metrics": {
                "hits": 1,
                "misses": 1,
                "false_alarms": 1,
                "correct_negatives": 1,
                "csi": csi,
                "pod": 0.5,
                "far": 0.5,
            },
            "valid_pixel_count": 4,
            "ignored_pixel_count": 0,
        }

    return EventModelComparison(
        event_id=event_id,
        split=split,
        persistence_rmse=10.0,
        persistence_csi=0.2,
        tiny_unet_rmse=tiny_rmse,
        tiny_unet_csi=tiny_csi,
        rmse_delta_tiny_unet_minus_persistence=tiny_rmse - 10.0,
        csi_delta_tiny_unet_minus_persistence=tiny_csi - 0.2,
        persistence_lead_time_metrics=[lead(10.0, 0.2)],
        tiny_unet_lead_time_metrics=[lead(tiny_rmse, tiny_csi)],
        artifact=ArtifactRecord(
            kind="evaluation",
            path=f"reports/{event_id}.json",
            sha256="a" * 64,
            bytes=10,
        ),
    )


def test_dataset_manifest_requires_real_event_minimums(tmp_path: Path):
    manifest = load_dataset_manifest(write_manifest(tmp_path, manifest_payload()))

    assert len(manifest.splits["train"]) == 2
    assert len(manifest.splits["validation"]) == 1
    assert len(manifest.splits["test"]) == 2
    assert all(not event.event_id.startswith("demo_") for event in manifest.events)


def test_promotion_gate_requires_all_independent_splits_to_beat_persistence():
    comparisons = [
        model_comparison("validation_one", "validation"),
        model_comparison("test_one", "test"),
    ]

    assert promotion_gate_failures(comparisons) == []

    tied_test = model_comparison("test_one", "test", tiny_csi=0.2)
    failures = promotion_gate_failures([comparisons[0], tied_test])
    assert failures == ["test_one: aggregate CSI did not beat persistence", "test_one: 10-minute CSI did not beat persistence"]


def test_promotion_gate_requires_validation_comparison():
    failures = promotion_gate_failures([model_comparison("test_one", "test")])

    assert "no independent validation comparison was produced" in failures


def test_dataset_manifest_rejects_demo_events(tmp_path: Path):
    payload = manifest_payload()
    payload["events"][0]["event_id"] = "demo_train"
    payload["splits"]["train"][0] = "demo_train"

    with pytest.raises(ValidationError, match="demo events are prohibited"):
        load_dataset_manifest(write_manifest(tmp_path, payload))


def test_dataset_manifest_requires_two_minxiong_test_events(tmp_path: Path):
    payload = manifest_payload()
    payload["events"][-1]["region"] = "Taiwan"

    with pytest.raises(ValidationError, match="at least 2 Minxiong events"):
        load_dataset_manifest(write_manifest(tmp_path, payload))


def test_dataset_manifest_rejects_overlapping_event_windows(tmp_path: Path):
    payload = manifest_payload()
    payload["events"][2]["start_time"] = payload["events"][0]["start_time"]
    payload["events"][2]["end_time"] = payload["events"][0]["end_time"]

    with pytest.raises(ValidationError, match="event windows overlap"):
        load_dataset_manifest(write_manifest(tmp_path, payload))


def test_expected_frame_count_includes_both_endpoints(tmp_path: Path):
    manifest = load_dataset_manifest(write_manifest(tmp_path, manifest_payload()))

    assert expected_frame_count(manifest.events[0], cadence_minutes=10) == 13


def test_artifact_record_is_relative_and_checksummed(tmp_path: Path):
    layout = ResearchLayout(tmp_path / "research")
    layout.ensure()
    artifact = layout.reports / "report.json"
    artifact.write_text('{"ok": true}\n', encoding="utf-8")

    record = artifact_record(layout, artifact, kind="report")

    assert record.path == "reports/report.json"
    assert record.bytes == artifact.stat().st_size
    assert len(record.sha256) == 64


def test_research_root_must_be_outside_repository(tmp_path: Path):
    repository = tmp_path / "repository"
    repository.mkdir()
    layout = ResearchLayout(repository / "research")

    with pytest.raises(ValueError, match="outside the Git repository"):
        require_external_research_root(layout, repository_root=repository)


def test_combine_split_archives_preserves_event_boundaries(tmp_path: Path):
    manifest = load_dataset_manifest(write_manifest(tmp_path, manifest_payload()))
    layout = ResearchLayout(tmp_path / "research")
    layout.ensure()
    spec = RadarTensorSpec(
        input_length=2,
        prediction_length=2,
        height=2,
        width=2,
        channels=1,
        cadence_minutes=10,
        units="dBZ",
        crs="TWD67",
    )
    for index, event_id in enumerate(manifest.splits["train"], start=1):
        write_tensor_archive(
            output_path=layout.tensors / f"{event_id}.npz",
            input_tensor=np.full((index, 2, 2, 2, 1), index, dtype=np.float32),
            target_tensor=np.full((index, 2, 2, 2, 1), index, dtype=np.float32),
            spec=spec,
            metadata={"event_id": event_id, "nodata_values": [-999.0]},
        )

    output = combine_split_archives(manifest=manifest, layout=layout, split="train")
    combined = load_tensor_archive(output)

    assert combined["input"].shape[0] == 3
    assert combined["metadata"]["event_ids"] == ["train_one", "train_two"]
    assert combined["metadata"]["event_sample_counts"] == {
        "train_one": 1,
        "train_two": 2,
    }


def test_resolve_catalog_artifact_path_rejects_root_escape(tmp_path: Path):
    layout = ResearchLayout(tmp_path / "research")
    layout.ensure()
    artifact = ArtifactRecord(
        kind="tensor_archive",
        path="../outside.npz",
        sha256="0" * 64,
        bytes=1,
    )

    with pytest.raises(ValueError, match="escapes root"):
        resolve_catalog_artifact_path(
            artifact=artifact,
            layout=layout,
            repository_root=tmp_path,
        )


def test_dataset_verification_report_is_schema_valid():
    report = DatasetVerificationReport(
        verified_at="2026-07-13T13:00:00+08:00",
        status="ok",
        catalog=ArtifactRecord(
            kind="dataset_catalog",
            path="catalog/dataset_catalog.json",
            sha256="a" * 64,
            bytes=10,
        ),
        artifact_count=3,
        total_bytes=100,
        mismatches=[],
    )

    assert report.status == "ok"
    assert report.artifact_count == 3
