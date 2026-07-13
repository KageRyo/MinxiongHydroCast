import json
from pathlib import Path

from minxionghydrocast.pipelines.qpe_gauge_validation import (
    build_qpe_gauge_report,
    extract_gauge_observations,
    extract_gauge_observations_from_xml,
    load_gauge_observations,
    qpe_grid_index_for_point,
    summarize_matches,
)
from minxionghydrocast.ingestion.cwa_grid import inspect_cwa_grid_file


def write_qpe_grid(path: Path) -> None:
    payload = {
        "cwaopendata": {
            "sent": "2026-07-02T15:06:44+08:00",
            "dataid": "O-B0045-001",
            "source": "CWA",
            "dataset": {
                "datasetInfo": {
                    "datasetDescription": "降雨估計資料",
                    "parameterSet": {
                        "StartPointLongitude": "120.0",
                        "StartPointLatitude": "23.0",
                        "GridResolution": "0.1",
                        "DateTime": "2026-07-02T15:00:00+08:00",
                        "GridDimensionX": "3",
                        "GridDimensionY": "2",
                        "Precipitation": "mm",
                    },
                },
                "contents": {
                    "contentDescription": "資料無效值為-1。使用之座標系統為TWD67經緯網格。",
                    "content": "1,2,3,4,5,-1",
                },
            },
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_gauges(path: Path) -> None:
    payload = {
        "cwaopendata": {
            "dataset": {
                "Station": [
                    {
                        "StationId": "C0M000",
                        "StationName": "民雄",
                        "ObsTime": {"DateTime": "2026-07-02T15:00:00+08:00"},
                        "GeoInfo": {
                            "Coordinates": [
                                {
                                    "CoordinateName": "WGS84",
                                    "StationLatitude": "23.1",
                                    "StationLongitude": "120.1",
                                }
                            ]
                        },
                        "RainfallElement": {"Past1hr": "6.5"},
                    },
                    {
                        "StationId": "C0M001",
                        "StationName": "網寮",
                        "ObsTime": {"DateTime": "2026-07-02T15:00:00+08:00"},
                        "GeoInfo": {
                            "Coordinates": [
                                {
                                    "CoordinateName": "WGS84",
                                    "StationLatitude": "23.1",
                                    "StationLongitude": "120.0",
                                }
                            ]
                        },
                        "RainfallElement": {"Past1hr": "1.0"},
                    },
                    {
                        "StationId": "OUTSIDE",
                        "StationName": "外海",
                        "ObsTime": {"DateTime": "2026-07-02T15:00:00+08:00"},
                        "GeoInfo": {
                            "Coordinates": [
                                {
                                    "CoordinateName": "WGS84",
                                    "StationLatitude": "25.0",
                                    "StationLongitude": "122.0",
                                }
                            ]
                        },
                        "RainfallElement": {"Past1hr": "9.0"},
                    },
                    {
                        "StationId": "NODATA",
                        "StationName": "無資料格點",
                        "ObsTime": {"DateTime": "2026-07-02T15:00:00+08:00"},
                        "GeoInfo": {
                            "Coordinates": [
                                {
                                    "CoordinateName": "WGS84",
                                    "StationLatitude": "23.1",
                                    "StationLongitude": "120.2",
                                }
                            ]
                        },
                        "RainfallElement": {"Past1hr": "3.0"},
                    },
                ]
            }
        }
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def write_xml_gauges(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<cwaopendata xmlns="urn:cwa:gov:tw:cwacommon:0.1">
  <dataset>
    <Station>
      <StationName>民雄</StationName>
      <StationId>C0M760</StationId>
      <ObsTime>
        <DateTime>2026-07-02T15:30:00+08:00</DateTime>
      </ObsTime>
      <GeoInfo>
        <Coordinates>
          <CoordinateName>TWD67</CoordinateName>
          <StationLatitude>23.560000</StationLatitude>
          <StationLongitude>120.420000</StationLongitude>
        </Coordinates>
        <Coordinates>
          <CoordinateName>WGS84</CoordinateName>
          <StationLatitude>23.558200</StationLatitude>
          <StationLongitude>120.428100</StationLongitude>
        </Coordinates>
      </GeoInfo>
      <RainfallElement>
        <Past1hr>
          <Precipitation>31.0</Precipitation>
        </Past1hr>
      </RainfallElement>
    </Station>
    <Station>
      <StationName>缺雨量</StationName>
      <StationId>MISSING</StationId>
      <ObsTime>
        <DateTime>2026-07-02T15:30:00+08:00</DateTime>
      </ObsTime>
      <GeoInfo>
        <Coordinates>
          <CoordinateName>WGS84</CoordinateName>
          <StationLatitude>23.1</StationLatitude>
          <StationLongitude>120.1</StationLongitude>
        </Coordinates>
      </GeoInfo>
      <RainfallElement>
        <Past1hr>
          <Precipitation>-99.0</Precipitation>
        </Past1hr>
      </RainfallElement>
    </Station>
  </dataset>
</cwaopendata>
""",
        encoding="utf-8",
    )


def test_extract_gauge_observations_from_cwa_like_payload(tmp_path: Path):
    gauge_path = tmp_path / "gauges.json"
    write_gauges(gauge_path)

    observations = extract_gauge_observations(
        json.loads(gauge_path.read_text(encoding="utf-8"))
    )

    assert len(observations) == 4
    assert observations[0].station_id == "C0M000"
    assert observations[0].station_name == "民雄"
    assert observations[0].latitude == 23.1
    assert observations[0].longitude == 120.1
    assert observations[0].rainfall_mm == 6.5


def test_extract_gauge_observations_from_cwa_xml_prefers_wgs84(tmp_path: Path):
    gauge_path = tmp_path / "gauges.xml"
    write_xml_gauges(gauge_path)

    observations = extract_gauge_observations_from_xml(
        gauge_path.read_text(encoding="utf-8")
    )

    assert len(observations) == 1
    assert observations[0].station_id == "C0M760"
    assert observations[0].station_name == "民雄"
    assert observations[0].data_time == "2026-07-02T15:30:00+08:00"
    assert observations[0].latitude == 23.5582
    assert observations[0].longitude == 120.4281
    assert observations[0].rainfall_mm == 31.0


def test_load_gauge_observations_detects_xml_even_with_json_suffix(tmp_path: Path):
    gauge_path = tmp_path / "gauges.json"
    write_xml_gauges(gauge_path)

    observations = load_gauge_observations(gauge_path)

    assert [observation.station_id for observation in observations] == ["C0M760"]


def test_extract_gauge_observations_dedupes_name_only_stations_separately():
    payload = {
        "stations": [
            {
                "StationName": "甲站",
                "DateTime": "2026-07-02T15:00:00+08:00",
                "StationLatitude": "23.1",
                "StationLongitude": "120.1",
                "Past1hr": "1.0",
            },
            {
                "StationName": "乙站",
                "DateTime": "2026-07-02T15:00:00+08:00",
                "StationLatitude": "23.2",
                "StationLongitude": "120.2",
                "Past1hr": "2.0",
            },
        ]
    }

    observations = extract_gauge_observations(payload)

    assert [observation.station_name for observation in observations] == ["甲站", "乙站"]


def test_qpe_grid_index_uses_south_to_north_rows(tmp_path: Path):
    qpe_path = tmp_path / "qpe.json"
    write_qpe_grid(qpe_path)
    inspection = inspect_cwa_grid_file(qpe_path)

    assert qpe_grid_index_for_point(inspection, latitude=23.1, longitude=120.1) == (1, 1)
    assert qpe_grid_index_for_point(inspection, latitude=25.0, longitude=122.0) is None


def test_build_qpe_gauge_report_computes_error_metrics(tmp_path: Path):
    qpe_path = tmp_path / "qpe.json"
    gauge_path = tmp_path / "gauges.json"
    write_qpe_grid(qpe_path)
    write_gauges(gauge_path)

    report = build_qpe_gauge_report(
        qpe_grid_path=qpe_path,
        gauge_json_path=gauge_path,
        event_id="event_a",
    )

    assert report["event_id"] == "event_a"
    assert report["qpe_source"]["data_id"] == "O-B0045-001"
    assert report["gauge_source"]["format"] == "json"
    assert report["summary"]["status"] == "ok"
    assert report["summary"]["gauge_count"] == 4
    assert report["summary"]["matched_gauge_count"] == 2
    assert report["summary"]["excluded_reasons"] == {"outside_qpe_grid": 1, "qpe_nodata": 1}
    assert report["summary"]["mae_mm"] == 2.25
    assert report["summary"]["rmse_mm"] == 2.371708
    assert report["summary"]["bias_mm"] == 0.75
    assert report["matches"][0]["qpe_mm"] == 5.0
    assert report["matches"][0]["difference_mm"] == -1.5
    assert report["matches"][1]["qpe_mm"] == 4.0
    assert report["matches"][2]["status"] == "excluded"
    assert report["matches"][2]["reason"] == "outside_qpe_grid"
    assert report["matches"][3]["status"] == "excluded"
    assert report["matches"][3]["reason"] == "qpe_nodata"


def test_summarize_matches_reports_no_matches():
    summary = summarize_matches([])

    assert summary["status"] == "no_matches"
    assert summary["matched_gauge_count"] == 0
    assert summary["mae_mm"] is None
