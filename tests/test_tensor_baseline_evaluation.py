from pathlib import Path

import numpy as np

from minxionghydrocast.models.radar_tensor import RadarTensorSpec
from minxionghydrocast.pipelines.radar_tensor_conversion import (
    convert_records,
    read_pixel_records,
    write_tensor_archive,
)
from minxionghydrocast.pipelines.tensor_baseline_evaluation import (
    evaluate_persistence_tensor_archive,
    write_evaluation_result,
)


def build_sample_archive(path: Path) -> None:
    records = read_pixel_records(Path("data/samples/radar_pixels.csv"))
    inputs, targets, spec, metadata = convert_records(
        records,
        event_id=None,
        input_length=3,
        prediction_length=2,
    )
    write_tensor_archive(
        output_path=path,
        input_tensor=inputs,
        target_tensor=targets,
        spec=spec,
        metadata=metadata,
    )


def test_evaluate_persistence_tensor_archive_reports_metrics(tmp_path: Path):
    archive_path = tmp_path / "radar_tensor_sample.npz"
    build_sample_archive(archive_path)

    result = evaluate_persistence_tensor_archive(
        archive_path=archive_path,
        event_threshold_mm=10.0,
    )

    assert result["model"] == "PersistenceNowcaster"
    assert result["event_id"] == "demo_extreme_test_2025"
    assert result["input_shape"] == [3, 2, 2, 1]
    assert result["target_shape"] == [2, 2, 2, 1]
    assert result["rmse_mm"] == 2.95804
    assert result["rmse"] == 2.95804
    assert result["value_units"] == "mm_per_hour"
    assert result["event_threshold_units"] == "mm_per_hour"
    assert result["event_metrics"]["csi"] == 0.5
    assert result["event_metrics"]["pod"] == 0.5
    assert result["event_metrics"]["far"] == 0.0


def test_evaluate_persistence_tensor_archive_ignores_nodata_pixels(tmp_path: Path):
    archive_path = tmp_path / "masked_radar_tensor.npz"
    input_tensor = np.array(
        [[[[1.0], [10.0]], [[-999.0], [30.0]]]],
        dtype=np.float32,
    )
    target_tensor = np.array(
        [[[[2.0], [10.0]], [[50.0], [-999.0]]]],
        dtype=np.float32,
    )
    write_tensor_archive(
        output_path=archive_path,
        input_tensor=input_tensor,
        target_tensor=target_tensor,
        spec=RadarTensorSpec(
            input_length=1,
            prediction_length=1,
            height=2,
            width=2,
            units="dBZ",
            crs="TWD67",
        ),
        metadata={"event_id": "masked_event", "nodata_values": [-999.0]},
    )

    result = evaluate_persistence_tensor_archive(
        archive_path=archive_path,
        event_threshold_mm=5.0,
    )

    assert result["rmse"] == 0.707107
    assert result["valid_pixel_count"] == 2
    assert result["ignored_pixel_count"] == 2
    assert result["event_metrics"]["hits"] == 1
    assert result["event_metrics"]["correct_negatives"] == 1


def test_evaluate_persistence_tensor_archive_reports_lead_times_for_sliding_windows(
    tmp_path: Path,
):
    archive_path = tmp_path / "sliding_radar_tensor.npz"
    input_tensor = np.array(
        [
            [[[[1.0]]]],
            [[[[10.0]]]],
        ],
        dtype=np.float32,
    )
    target_tensor = np.array(
        [
            [[[[3.0]]], [[[4.0]]]],
            [[[[30.0]]], [[[40.0]]]],
        ],
        dtype=np.float32,
    )
    write_tensor_archive(
        output_path=archive_path,
        input_tensor=input_tensor,
        target_tensor=target_tensor,
        spec=RadarTensorSpec(
            input_length=1,
            prediction_length=2,
            height=1,
            width=1,
            units="dBZ",
            cadence_minutes=10,
        ),
        metadata={
            "event_id": "sliding_event",
            "archive_layout": "sliding_window",
            "window_count": 2,
        },
    )

    result = evaluate_persistence_tensor_archive(
        archive_path=archive_path,
        event_threshold_mm=5.0,
    )

    assert result["archive_layout"] == "sliding_window"
    assert result["window_count"] == 2
    assert result["horizon"] == 2
    assert [item["lead_time_minutes"] for item in result["lead_time_metrics"]] == [10, 20]
    assert result["lead_time_metrics"][0]["valid_pixel_count"] == 2
    assert result["lead_time_metrics"][1]["valid_pixel_count"] == 2


def test_write_tensor_baseline_evaluation_result(tmp_path: Path):
    archive_path = tmp_path / "radar_tensor_sample.npz"
    build_sample_archive(archive_path)
    output = tmp_path / "tensor_baseline_evaluation.json"
    result = evaluate_persistence_tensor_archive(archive_path=archive_path)

    write_evaluation_result(result, output)

    assert '"model": "PersistenceNowcaster"' in output.read_text(encoding="utf-8")
