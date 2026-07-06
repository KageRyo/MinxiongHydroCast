import json
from pathlib import Path

from floodcasttw.ingestion.cwa_grid import inspect_cwa_grid_file


def write_sample_grid(
    path: Path,
    *,
    data_id: str = "O-A0059-001",
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
                        "DateTime": "2026-07-06T19:30:00+08:00",
                        "GridDimensionX": "2",
                        "GridDimensionY": "2",
                        "Reflectivity": "dBZ",
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


def test_inspect_cwa_grid_detects_value_count_mismatch(tmp_path: Path):
    path = tmp_path / "O-A0059-001.json"
    write_sample_grid(path, content="1.000E+00,2.000E+00,3.000E+00")

    inspection = inspect_cwa_grid_file(path)

    assert inspection.expected_value_count == 4
    assert inspection.value_count == 3
    assert inspection.valid is False
