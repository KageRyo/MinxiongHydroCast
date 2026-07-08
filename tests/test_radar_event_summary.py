import json
from pathlib import Path

from floodcasttw.pipelines.radar_event_summary import (
    grid_xy_for_lon_lat,
    summarize_event_collection,
)
from floodcasttw.ingestion.cwa_grid import inspect_cwa_grid_file


def write_grid(
    path: Path,
    *,
    data_time: str,
    content: str,
) -> None:
    payload = {
        "cwaopendata": {
            "sent": "2026-07-06T19:36:44+08:00",
            "dataid": "O-A0059-001",
            "source": "CWA",
            "dataset": {
                "datasetInfo": {
                    "datasetDescription": "雷達合成回波",
                    "parameterSet": {
                        "StartPointLongitude": "115.0",
                        "StartPointLatitude": "18.0",
                        "GridResolution": "0.0125",
                        "DateTime": data_time,
                        "GridDimensionX": "3",
                        "GridDimensionY": "3",
                        "Reflectivity": "dBZ",
                    },
                },
                "contents": {
                    "contentDescription": (
                        "資料無效值為-99，觀測範圍外以-999表示。"
                        "使用之座標系統為TWD67。"
                    ),
                    "content": content,
                },
            },
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_collection(path: Path, frame_paths: list[Path]) -> None:
    payload = {
        "event_id": "synthetic_chiayi_window",
        "data_id": "O-A0059-001",
        "frame_count": len(frame_paths),
        "bytes_written": 0,
        "frames": [
            {
                "data_time": f"2026-07-06T19:{30 + index * 10:02d}:00+08:00",
                "source_url": "https://example.test?Authorization=REDACTED",
                "output_path": str(frame_path),
                "bytes_written": frame_path.stat().st_size,
            }
            for index, frame_path in enumerate(frame_paths)
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_grid_xy_for_lon_lat_maps_local_focus_pixel(tmp_path: Path):
    frame = tmp_path / "frame.json"
    write_grid(frame, data_time="2026-07-06T19:30:00+08:00", content="1,2,3,4,5,6,7,8,9")
    inspection = inspect_cwa_grid_file(frame)

    assert grid_xy_for_lon_lat(inspection, longitude=115.0125, latitude=18.0125) == (1, 1)


def test_summarize_event_collection_reports_local_and_taiwan_thresholds(tmp_path: Path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    write_grid(
        first,
        data_time="2026-07-06T19:30:00+08:00",
        content="-999,-99,1,2,41,3,4,5,6",
    )
    write_grid(
        second,
        data_time="2026-07-06T19:40:00+08:00",
        content="1,2,3,4,5,6,7,8,55",
    )
    collection = tmp_path / "collection.json"
    write_collection(collection, [first, second])

    summary = summarize_event_collection(
        collection,
        local_name="synthetic focus",
        local_longitude=115.0125,
        local_latitude=18.0125,
        local_radius_pixels=0,
        event_threshold=35.0,
    )

    assert summary["event_id"] == "synthetic_chiayi_window"
    assert summary["frame_count"] == 2
    assert summary["sequence_check"]["status"] == "ok"
    assert summary["candidate_labels"] == [
        "chiayi_minxiong_heavy_rain_radar_candidate",
        "taiwan_wide_widespread_radar_candidate",
    ]
    assert summary["local_focus"]["frames_over_threshold"] == 1
    assert summary["local_focus"]["peak_max_value"] == 41.0
    assert summary["local_focus"]["coverage_peak_time"] == "2026-07-06T19:30:00+08:00"
    assert summary["local_focus"]["coverage_peak_pixels_ge_threshold"] == 1
    assert summary["taiwan_wide"]["frames_over_threshold"] == 2
    assert summary["taiwan_wide"]["peak_max_value"] == 55.0
    assert summary["taiwan_wide"]["coverage_peak_time"] == "2026-07-06T19:40:00+08:00"
    assert summary["taiwan_wide"]["coverage_peak_pixels_ge_threshold"] == 1
    assert summary["frames"][0]["grid"]["valid_pixel_count"] == 7
