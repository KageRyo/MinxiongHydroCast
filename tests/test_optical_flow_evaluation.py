import json
from pathlib import Path

import numpy as np

from minxionghydrocast.models.radar_tensor import RadarTensorSpec
from minxionghydrocast.pipelines.optical_flow_evaluation import (
    evaluate_optical_flow_tensor_archive,
    write_evaluation_result,
)
from minxionghydrocast.pipelines.radar_tensor_conversion import write_tensor_archive


def translated(frame: np.ndarray, row_shift: int, column_shift: int) -> np.ndarray:
    output = np.zeros_like(frame)
    height, width = frame.shape
    source_row_start = max(0, -row_shift)
    source_row_end = min(height, height - row_shift)
    source_column_start = max(0, -column_shift)
    source_column_end = min(width, width - column_shift)
    if source_row_start >= source_row_end or source_column_start >= source_column_end:
        return output
    output[
        source_row_start + row_shift : source_row_end + row_shift,
        source_column_start + column_shift : source_column_end + column_shift,
    ] = frame[source_row_start:source_row_end, source_column_start:source_column_end]
    return output


def write_moving_archive(path: Path, *, sliding: bool = False) -> None:
    base = np.zeros((40, 40), dtype=np.float32)
    base[10:16, 8:13] = 45.0
    base[23:27, 27:31] = 20.0
    sequence = np.stack([translated(base, 0, index * 2) for index in range(5)])
    spec = RadarTensorSpec(
        input_length=3,
        prediction_length=2,
        height=40,
        width=40,
        channels=1,
        cadence_minutes=10,
        units="dBZ",
        crs="TWD67",
    )
    if sliding:
        vertical_sequence = np.stack([translated(base, index, 0) for index in range(5)])
        input_tensor = np.stack(
            [sequence[:3, ..., np.newaxis], vertical_sequence[:3, ..., np.newaxis]]
        )
        target_tensor = np.stack(
            [sequence[3:, ..., np.newaxis], vertical_sequence[3:, ..., np.newaxis]]
        )
        metadata = {
            "event_id": "sliding_optical_flow_event",
            "archive_layout": "sliding_window",
            "window_count": 2,
            "nodata_values": [-999.0, -99.0],
        }
    else:
        input_tensor = sequence[:3, ..., np.newaxis]
        target_tensor = sequence[3:, ..., np.newaxis]
        metadata = {
            "event_id": "optical_flow_event",
            "nodata_values": [-999.0, -99.0],
        }
    write_tensor_archive(
        output_path=path,
        input_tensor=input_tensor,
        target_tensor=target_tensor,
        spec=spec,
        metadata=metadata,
    )


def test_optical_flow_evaluation_reports_mae_and_lead_times(tmp_path: Path):
    archive = tmp_path / "moving.npz"
    write_moving_archive(archive)

    result = evaluate_optical_flow_tensor_archive(
        archive_path=archive,
        event_threshold=35.0,
        max_displacement=8,
        min_valid_pixels=8,
    )

    assert result["event_id"] == "optical_flow_event"
    assert set(result["models"]) == {"PersistenceNowcaster", "OpticalFlowNowcaster"}
    assert result["models"]["OpticalFlowNowcaster"]["rmse"] == 0.0
    assert result["models"]["OpticalFlowNowcaster"]["mae"] == 0.0
    assert [
        item["lead_time_minutes"]
        for item in result["models"]["OpticalFlowNowcaster"]["lead_time_metrics"]
    ] == [10, 20]
    assert result["optical_flow_metadata"]["deterministic"] is True
    assert result["comparison"]["rmse_delta_optical_flow_minus_persistence"] < 0.0


def test_optical_flow_evaluation_keeps_sliding_windows_independent(tmp_path: Path):
    archive = tmp_path / "sliding.npz"
    write_moving_archive(archive, sliding=True)

    result = evaluate_optical_flow_tensor_archive(
        archive_path=archive,
        event_threshold=35.0,
        max_displacement=8,
        min_valid_pixels=8,
    )

    assert result["archive_layout"] == "sliding_window"
    assert result["window_count"] == 2
    assert result["input_shape"] == [2, 3, 40, 40, 1]
    assert result["target_shape"] == [2, 2, 40, 40, 1]
    assert result["models"]["OpticalFlowNowcaster"]["valid_pixel_count"] > 0


def test_write_optical_flow_evaluation_result_validates_schema(tmp_path: Path):
    archive = tmp_path / "moving.npz"
    output = tmp_path / "optical-flow.json"
    write_moving_archive(archive)
    result = evaluate_optical_flow_tensor_archive(archive_path=archive, max_displacement=8)

    write_evaluation_result(result, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["models"]["OpticalFlowNowcaster"]["mae"] == 0.0
    assert payload["optical_flow_metadata"]["motion_estimator"] == "fft_phase_correlation"
