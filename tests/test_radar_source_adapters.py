from pathlib import Path

from floodcasttw.pipelines.radar_source_adapters import (
    CSV_PIXEL_GRID,
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
