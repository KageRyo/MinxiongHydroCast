from pathlib import Path

from floodcasttw.pipelines.radar_tensor_conversion import (
    convert_records,
    read_pixel_records,
    write_tensor_archive,
)
from floodcasttw.pipelines.tensor_baseline_evaluation import (
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
    assert result["event_metrics"]["csi"] == 0.5
    assert result["event_metrics"]["pod"] == 0.5
    assert result["event_metrics"]["far"] == 0.0


def test_write_tensor_baseline_evaluation_result(tmp_path: Path):
    output = tmp_path / "tensor_baseline_evaluation.json"
    result = {
        "model": "PersistenceNowcaster",
        "rmse_mm": 4.0,
    }

    write_evaluation_result(result, output)

    assert '"rmse_mm": 4.0' in output.read_text(encoding="utf-8")
