import json
from pathlib import Path

from floodcasttw.pipelines.radar_source_adapters import (
    CWA_OPEN_DATA_GRID,
    CSV_PIXEL_GRID,
    CwaOpenDataGridAdapter,
    CsvPixelGridAdapter,
    get_radar_source_adapter,
    read_csv_pixel_records,
)


def test_csv_pixel_grid_adapter_loads_sample_sequence():
    adapter = CsvPixelGridAdapter()
    batch = adapter.load_sequence(
        input_path=Path("data/samples/radar_pixels.csv"),
        event_id=None,
        input_length=3,
        prediction_length=2,
    )

    assert batch.event_id == "demo_extreme_test_2025"
    assert batch.source_format == CSV_PIXEL_GRID
    assert batch.sequence.shape == (5, 2, 2, 1)
    assert batch.metadata["source_path"] == "data/samples/radar_pixels.csv"
    assert batch.source_record_count == 20


def write_cwa_grid(path: Path, *, data_time: str, values: str) -> None:
    path.write_text(
        """
{
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
          "DateTime": "%s",
          "GridDimensionX": "2",
          "GridDimensionY": "2",
          "Reflectivity": "dBZ"
        }
      },
      "contents": {
        "contentDescription": "資料無效值為-99，觀測範圍外以-999表示。使用之座標系統為TWD67。",
        "content": "%s"
      }
    }
  }
}
"""
        % (data_time, values),
        encoding="utf-8",
    )


def test_cwa_open_data_grid_adapter_loads_collection_manifest(tmp_path: Path):
    frames = []
    for index, data_time in enumerate(
        [
            "2026-07-06T19:30:00+08:00",
            "2026-07-06T19:40:00+08:00",
            "2026-07-06T19:50:00+08:00",
        ]
    ):
        path = tmp_path / f"frame_{index}.json"
        write_cwa_grid(path, data_time=data_time, values=f"{index},1,2,3")
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

    batch = CwaOpenDataGridAdapter().load_sequence(
        input_path=manifest,
        event_id=None,
        input_length=2,
        prediction_length=1,
        cadence_minutes=10,
    )

    assert batch.event_id == "sample_cwa_event"
    assert batch.source_format == CWA_OPEN_DATA_GRID
    assert batch.sequence.shape == (3, 2, 2, 1)
    assert batch.spec.units == "dBZ"
    assert batch.spec.crs == "TWD67"
    assert batch.metadata["cwa_data_id"] == "O-A0059-001"
    assert batch.metadata["sequence_check"]["status"] == "ok"
    assert batch.source_record_count == 12


def test_radar_source_adapter_registry_rejects_unknown_format():
    try:
        get_radar_source_adapter("unknown")
    except ValueError as exc:
        assert "unsupported radar source format" in str(exc)
    else:
        raise AssertionError("expected unknown radar source format to fail")


def test_csv_pixel_reader_validates_required_fields(tmp_path: Path):
    bad_csv = tmp_path / "bad_radar_pixels.csv"
    bad_csv.write_text("event_id,frame_index,y,x\nexample,0,0,0\n", encoding="utf-8")

    try:
        read_csv_pixel_records(bad_csv)
    except ValueError as exc:
        assert "missing radar pixel fields" in str(exc)
    else:
        raise AssertionError("expected missing field validation to fail")
