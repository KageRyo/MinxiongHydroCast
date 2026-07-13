from pathlib import Path
import json

import numpy as np

from minxionghydrocast.models.baselines import PersistenceNowcaster
from minxionghydrocast.pipelines.radar_tensor_conversion import (
    convert_source,
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


def write_cwa_grid(path: Path, *, data_time: str, values: str) -> None:
    payload = {
        "cwaopendata": {
            "sent": "2026-07-06T19:36:44+08:00",
            "dataid": "O-A0059-001",
            "dataset": {
                "datasetInfo": {
                    "datasetDescription": "雷達合成回波",
                    "parameterSet": {
                        "StartPointLongitude": "115.0",
                        "StartPointLatitude": "18.0",
                        "GridResolution": "0.0125",
                        "DateTime": data_time,
                        "GridDimensionX": "2",
                        "GridDimensionY": "2",
                        "Reflectivity": "dBZ",
                    },
                },
                "contents": {
                    "contentDescription": (
                        "資料無效值為-99，觀測範圍外以-999表示。"
                        "使用之座標系統為TWD67。"
                    ),
                    "content": values,
                },
            },
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_convert_cwa_collection_to_sliding_window_tensors(tmp_path: Path):
    frames = []
    for index, minute in enumerate([0, 10, 20, 30, 40]):
        path = tmp_path / f"frame_{index}.json"
        write_cwa_grid(
            path,
            data_time=f"2026-07-06T19:{minute:02d}:00+08:00",
            values=f"{index},1,2,3",
        )
        frames.append({"output_path": str(path)})
    manifest = tmp_path / "collection.json"
    manifest.write_text(
        json.dumps(
            {
                "event_id": "sample_cwa_event",
                "data_id": "O-A0059-001",
                "frames": frames,
            }
        ),
        encoding="utf-8",
    )

    inputs, targets, spec, metadata, record_count = convert_source(
        input_path=manifest,
        source_format="cwa_opendata_grid",
        event_id=None,
        input_length=2,
        prediction_length=2,
        cadence_minutes=10,
        window_stride_frames=1,
    )

    assert inputs.shape == (2, 2, 2, 2, 1)
    assert targets.shape == (2, 2, 2, 2, 1)
    assert spec.total_length == 4
    assert metadata["archive_layout"] == "sliding_window"
    assert metadata["window_count"] == 2
    assert metadata["window_start_indices"] == [0, 1]
    assert metadata["target_lead_times_minutes"] == [10, 20]
    assert record_count == 20
    assert float(inputs[1, 0, 0, 0, 0]) == 1.0
    assert float(targets[1, 1, 0, 0, 0]) == 4.0
