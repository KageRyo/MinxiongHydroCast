import json
from pathlib import Path

from floodcasttw.ingestion.radar_sources import RadarSource, load_manifest


def test_candidate_radar_source_reports_missing_fields():
    source = RadarSource(
        name="candidate",
        status="candidate",
        provider="Central Weather Administration, Taiwan",
        source_url="https://example.test/radar",
        local_path=Path("data/external/radar/example"),
    )

    assert source.is_confirmed() is False
    assert "native_format" in source.missing_confirmation_fields()
    assert "cadence_minutes" in source.missing_confirmation_fields()


def test_confirmed_radar_source_passes_manifest_check(tmp_path: Path):
    manifest_path = tmp_path / "radar_source_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "selected_source": "confirmed",
                "sources": [
                    {
                        "name": "confirmed",
                        "status": "confirmed",
                        "provider": "Example Provider",
                        "source_url": "https://example.test/radar",
                        "documentation_url": "https://example.test/docs",
                        "license": "Example Open License",
                        "license_url": "https://example.test/license",
                        "access_method": "download",
                        "native_format": "NetCDF",
                        "cadence_minutes": 10,
                        "crs": "EPSG:4326",
                        "grid": "100x100 lat/lon",
                        "units": "mm_per_hour",
                        "local_path": str(tmp_path / "radar"),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_manifest(manifest_path)
    result = manifest.check()

    assert result["status"] == "ok"
    assert result["errors"] == []


def test_sample_manifest_requires_review():
    manifest = load_manifest(Path("data/samples/radar_source_manifest.json"))
    result = manifest.check()

    assert result["status"] == "needs_review"
    assert result["selected_source"] == "cwa_qpesums_radar_echo_grid"
    assert result["errors"]

    selected = manifest.selected()
    assert selected is not None
    assert selected.data_id == "O-A0059-001"
    assert selected.cadence_minutes == 10
    assert selected.units == "dBZ"
    assert "Confirm CRS/EPSG from a downloaded sample file." in selected.known_gaps
