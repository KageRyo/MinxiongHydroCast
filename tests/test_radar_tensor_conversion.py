from pathlib import Path

import numpy as np

from floodcasttw.models.baselines import PersistenceNowcaster
from floodcasttw.pipelines.radar_tensor_conversion import (
    convert_records,
    load_tensor_archive,
    read_pixel_records,
    write_tensor_archive,
)


def test_convert_sample_radar_pixels_to_tensors():
    records = read_pixel_records(Path("data/samples/radar_pixels.csv"))
    inputs, targets, spec, metadata = convert_records(
        records,
        event_id="demo_extreme_test_2025",
        input_length=3,
        prediction_length=2,
    )

    assert inputs.shape == (3, 2, 2, 1)
    assert targets.shape == (2, 2, 2, 1)
    assert spec.total_length == 5
    assert metadata["event_id"] == "demo_extreme_test_2025"
    assert float(inputs[-1, 1, 1, 0]) == 16.0
    assert float(targets[-1, 1, 1, 0]) == 22.0


def test_tensor_archive_roundtrip(tmp_path: Path):
    records = read_pixel_records(Path("data/samples/radar_pixels.csv"))
    inputs, targets, spec, metadata = convert_records(
        records,
        event_id=None,
        input_length=3,
        prediction_length=2,
    )
    output = tmp_path / "radar_tensor_sample.npz"

    write_tensor_archive(
        output_path=output,
        input_tensor=inputs,
        target_tensor=targets,
        spec=spec,
        metadata=metadata,
    )
    archive = load_tensor_archive(output)

    np.testing.assert_allclose(archive["input"], inputs)
    np.testing.assert_allclose(archive["target"], targets)
    assert archive["spec"]["height"] == 2
    assert archive["metadata"]["event_id"] == "demo_extreme_test_2025"


def test_converter_rejects_duplicate_pixels():
    records = read_pixel_records(Path("data/samples/radar_pixels.csv"))
    records.append(dict(records[0]))

    try:
        convert_records(records, event_id=None, input_length=3, prediction_length=2)
    except ValueError as exc:
        assert "duplicate pixel" in str(exc)
    else:
        raise AssertionError("expected duplicate pixel validation to fail")


def test_persistence_baseline_accepts_converted_tensor():
    records = read_pixel_records(Path("data/samples/radar_pixels.csv"))
    inputs, targets, _spec, _metadata = convert_records(
        records,
        event_id=None,
        input_length=3,
        prediction_length=2,
    )

    prediction = PersistenceNowcaster(horizon=targets.shape[0]).predict(inputs)

    assert prediction.shape == targets.shape
    np.testing.assert_allclose(prediction[0], inputs[-1])
