import json
from pathlib import Path

import pytest

from minxionghydrocast.models.event_splits import load_manifest
from minxionghydrocast.pipelines.optical_flow_report import (
    build_public_optical_flow_report,
    write_public_report,
)


def event_metrics() -> dict[str, object]:
    return {
        "hits": 1,
        "misses": 1,
        "false_alarms": 0,
        "correct_negatives": 2,
        "csi": 0.5,
        "pod": 0.5,
        "far": 0.0,
    }


def optical_model(*, mae: float, rmse: float) -> dict[str, object]:
    return {
        "rmse": rmse,
        "mae": mae,
        "event_metrics": event_metrics(),
        "valid_pixel_count": 4,
        "ignored_pixel_count": 0,
        "lead_time_metrics": [
            {
                "lead_index": 0,
                "lead_time_minutes": 10,
                "rmse": rmse,
                "mae": mae,
                "event_metrics": event_metrics(),
                "valid_pixel_count": 4,
                "ignored_pixel_count": 0,
            }
        ],
    }


def tiny_model(*, rmse: float) -> dict[str, object]:
    return {
        "rmse": rmse,
        "event_metrics": event_metrics(),
        "valid_pixel_count": 4,
        "ignored_pixel_count": 0,
        "lead_time_metrics": [
            {
                "lead_index": 0,
                "lead_time_minutes": 10,
                "rmse": rmse,
                "event_metrics": event_metrics(),
                "valid_pixel_count": 4,
                "ignored_pixel_count": 0,
            }
        ],
    }


def write_comparison_reports(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest_path = Path("data/samples/event_split_manifest.json")
    manifest = load_manifest(manifest_path)
    optical_dir = tmp_path / "optical"
    tiny_dir = tmp_path / "tiny"
    optical_dir.mkdir()
    tiny_dir.mkdir()
    split_by_id = {
        event_id: split
        for split, event_ids in manifest.splits.items()
        for event_id in event_ids
    }
    for event in manifest.events:
        split = split_by_id[event.event_id]
        optical_payload = {
            "generated_at": "2026-08-17T00:00:00+08:00",
            "archive": "/private/archive.npz",
            "event_id": event.event_id,
            "event_threshold": 35.0,
            "event_threshold_units": "dBZ",
            "value_units": "dBZ",
            "archive_layout": "sliding_window",
            "window_count": 2,
            "input_shape": [2, 6, 2, 2, 1],
            "target_shape": [2, 6, 2, 2, 1],
            "evaluation_mask": {"valid_pixel_count": 4, "ignored_pixel_count": 0},
            "models": {
                "PersistenceNowcaster": optical_model(mae=2.0, rmse=3.0),
                "OpticalFlowNowcaster": optical_model(mae=1.0, rmse=1.5),
            },
            "comparison": {
                "rmse_delta_optical_flow_minus_persistence": -1.5,
                "mae_delta_optical_flow_minus_persistence": -1.0,
                "csi_delta_optical_flow_minus_persistence": 0.0,
            },
            "optical_flow_metadata": {
                "motion_estimator": "fft_phase_correlation",
                "deterministic": True,
            },
            "tensor_spec": {"units": "dBZ"},
            "metadata": {"event_id": event.event_id, "model_split": split},
        }
        (optical_dir / f"{event.event_id}_optical_flow.json").write_text(
            json.dumps(optical_payload), encoding="utf-8"
        )
        if split in {"validation", "test"}:
            tiny_payload = {
                "generated_at": "2026-08-17T00:00:00+08:00",
                "archive": "/private/archive.npz",
                "checkpoint": "/private/checkpoint.pt",
                "event_id": event.event_id,
                "event_threshold": 35.0,
                "event_threshold_units": "dBZ",
                "value_units": "dBZ",
                "archive_layout": "sliding_window",
                "window_count": 2,
                "input_shape": [2, 6, 2, 2, 1],
                "target_shape": [2, 6, 2, 2, 1],
                "evaluation_mask": {"valid_pixel_count": 4, "ignored_pixel_count": 0},
                "models": {
                    "PersistenceNowcaster": tiny_model(rmse=3.0),
                    "TinyUNetNowcaster": tiny_model(rmse=2.0),
                },
                "comparison": {
                    "rmse_delta_tiny_unet_minus_persistence": -1.0,
                    "csi_delta_tiny_unet_minus_persistence": 0.0,
                },
                "tiny_unet_metadata": {
                    "checkpoint": "/private/checkpoint.pt",
                    "device": "cpu",
                    "normalization": {},
                    "nodata_values": [],
                    "hidden_channels": 2,
                    "batch_size": 1,
                },
                "tensor_spec": {"units": "dBZ"},
                "metadata": {"event_id": event.event_id, "model_split": split},
            }
            (tiny_dir / f"{event.event_id}_weighted_tiny_unet.json").write_text(
                json.dumps(tiny_payload), encoding="utf-8"
            )
    return manifest_path, optical_dir, tiny_dir


def test_public_report_compares_three_models_without_private_paths(tmp_path: Path):
    manifest_path, optical_dir, tiny_dir = write_comparison_reports(tmp_path)

    report = build_public_optical_flow_report(
        manifest_path=manifest_path,
        optical_flow_dir=optical_dir,
        tiny_unet_dir=tiny_dir,
    )

    assert len(report["events"]) == 5
    assert set(report["aggregate_by_split"]["independent"]) == {
        "PersistenceNowcaster",
        "OpticalFlowNowcaster",
        "TinyUNetNowcaster",
    }
    assert report["aggregate_by_split"]["independent"]["OpticalFlowNowcaster"]["mae"] == 1.0
    serialized = json.dumps(report)
    assert "archive" not in serialized
    assert "checkpoint" not in serialized
    output = tmp_path / "public-report.json"
    write_public_report(report, output)
    assert output.is_file()


def test_public_report_rejects_split_mixing(tmp_path: Path):
    manifest_path, optical_dir, tiny_dir = write_comparison_reports(tmp_path)
    event_id = load_manifest(manifest_path).splits["test"][0]
    report_path = optical_dir / f"{event_id}_optical_flow.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    payload["metadata"]["model_split"] = "train"
    report_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        build_public_optical_flow_report(
            manifest_path=manifest_path,
            optical_flow_dir=optical_dir,
            tiny_unet_dir=tiny_dir,
        )
