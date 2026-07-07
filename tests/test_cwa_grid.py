import json
from pathlib import Path

from floodcasttw.ingestion.cwa_grid import check_cwa_grid_sequence, inspect_cwa_grid_file


def write_sample_grid(
    path: Path,
    *,
    data_id: str = "O-A0059-001",
    data_time: str = "2026-07-06T19:30:00+08:00",
    grid_dimension_x: str = "2",
    grid_dimension_y: str = "2",
    units_field: str = "Reflectivity",
    units: str = "dBZ",
    content: str = "-9.990E+02,-9.900E+01,1.000E+00,4.710E+01",
) -> None:
    payload = {
        "cwaopendata": {
            "sent": "2026-07-06T19:36:44+08:00",
            "dataid": data_id,
            "source": "CWA",
            "dataset": {
                "datasetInfo": {
                    "datasetDescription": "雷達合成回波",
                    "parameterSet": {
                        "StartPointLongitude": "115.0",
                        "StartPointLatitude": "18.0",
                        "GridResolution": "0.0125",
                        "DateTime": data_time,
                        "GridDimensionX": grid_dimension_x,
                        "GridDimensionY": grid_dimension_y,
                        units_field: units,
                    },
                },
                "contents": {
                    "contentDescription": (
                        "資料無效值為-99，雷達觀測範圍外或經資料品管流程移除之資料"
                        "則以-999表示。左下角第一點之座標為東經115.0、北緯18.0，"
                        "依序先由西向東、再由南往北遞增。使用之座標系統為TWD67。"
                    ),
                    "content": content,
                },
            },
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_sample_grid_xml(
    path: Path,
    *,
    data_time: str = "2026-07-06T19:30:00+08:00",
    content: str = "-9.990E+02,-9.900E+01,1.000E+00,4.710E+01",
) -> None:
    payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
  <sent>2026-07-06T19:36:44+08:00</sent>
  <dataid>O-A0059-001</dataid>
  <dataset>
    <datasetInfo>
      <datasetDescription>雷達合成回波</datasetDescription>
      <parameterSet>
        <StartPointLongitude>115.0</StartPointLongitude>
        <StartPointLatitude>18.0</StartPointLatitude>
        <GridResolution>0.0125</GridResolution>
        <DateTime>{data_time}</DateTime>
        <GridDimensionX>2</GridDimensionX>
        <GridDimensionY>2</GridDimensionY>
        <Reflectivity>dBZ</Reflectivity>
      </parameterSet>
    </datasetInfo>
    <contents>
      <contentDescription>資料無效值為-99，觀測範圍外以-999表示。使用之座標系統為TWD67。</contentDescription>
      <content>{content}</content>
    </contents>
  </dataset>
</cwaopendata>
"""
    path.write_text(payload, encoding="utf-8")


def test_inspect_cwa_grid_extracts_schema(tmp_path: Path):
    path = tmp_path / "O-A0059-001.json"
    write_sample_grid(path)

    inspection = inspect_cwa_grid_file(path)

    assert inspection.data_id == "O-A0059-001"
    assert inspection.dataset_description == "雷達合成回波"
    assert inspection.data_time == "2026-07-06T19:30:00+08:00"
    assert inspection.start_longitude == 115.0
    assert inspection.start_latitude == 18.0
    assert inspection.grid_resolution == 0.0125
    assert inspection.grid_dimension_x == 2
    assert inspection.grid_dimension_y == 2
    assert inspection.expected_value_count == 4
    assert inspection.value_count == 4
    assert inspection.units == "dBZ"
    assert inspection.crs == "TWD67"
    assert inspection.nodata_values == (-999.0, -99.0)
    assert inspection.min_value == -999.0
    assert inspection.max_value == 47.1
    assert inspection.valid is True


def test_inspect_cwa_grid_extracts_xml_schema(tmp_path: Path):
    path = tmp_path / "O-A0059-001.xml"
    write_sample_grid_xml(path)

    inspection = inspect_cwa_grid_file(path)

    assert inspection.data_id == "O-A0059-001"
    assert inspection.dataset_description == "雷達合成回波"
    assert inspection.data_time == "2026-07-06T19:30:00+08:00"
    assert inspection.grid_dimension_x == 2
    assert inspection.grid_dimension_y == 2
    assert inspection.units == "dBZ"
    assert inspection.nodata_values == (-999.0, -99.0)
    assert inspection.valid is True


def test_inspect_cwa_grid_detects_value_count_mismatch(tmp_path: Path):
    path = tmp_path / "O-A0059-001.json"
    write_sample_grid(path, content="1.000E+00,2.000E+00,3.000E+00")

    inspection = inspect_cwa_grid_file(path)

    assert inspection.expected_value_count == 4
    assert inspection.value_count == 3
    assert inspection.valid is False


def test_check_cwa_grid_sequence_accepts_consistent_cadence(tmp_path: Path):
    paths = []
    for index, data_time in enumerate(
        [
            "2026-07-06T19:30:00+08:00",
            "2026-07-06T19:40:00+08:00",
            "2026-07-06T19:50:00+08:00",
        ]
    ):
        path = tmp_path / f"frame_{index}.json"
        write_sample_grid(path, data_time=data_time)
        paths.append(path)

    inspections = [inspect_cwa_grid_file(path) for path in paths]
    result = check_cwa_grid_sequence(inspections, expected_cadence_minutes=10)

    assert result["status"] == "ok"
    assert result["frame_count"] == 3
    assert result["observed_cadence_minutes"] == [10.0, 10.0]
    assert result["reference"]["grid_dimension_x"] == 2


def test_check_cwa_grid_sequence_flags_grid_and_cadence_changes(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_sample_grid(first, data_time="2026-07-06T19:30:00+08:00")
    write_sample_grid(
        second,
        data_time="2026-07-06T19:50:00+08:00",
        grid_dimension_x="3",
        content="1,2,3,4,5,6",
    )

    result = check_cwa_grid_sequence(
        [inspect_cwa_grid_file(first), inspect_cwa_grid_file(second)],
        expected_cadence_minutes=10,
    )

    assert result["status"] == "error"
    assert any("grid_dimension_x changed" in error for error in result["errors"])
    assert any("expected 10 minutes" in error for error in result["errors"])
