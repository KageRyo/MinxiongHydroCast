import json

import pytest
from pydantic import ValidationError

from minxionghydrocast.region_profiles import (
    available_region_profiles,
    load_region_boundary,
    load_region_profile,
)


def test_packaged_minxiong_profile_declares_operational_contract():
    profile = load_region_profile("minxiong")

    assert profile.region.id == "minxiong"
    assert profile.region.county_code == "10010"
    assert profile.region.township_code == "10010050"
    assert profile.region.timezone == "Asia/Taipei"
    assert profile.coverage.required_rain_gauges == 1
    assert profile.coverage.required_flood_sensors == 1
    assert profile.freshness.rain_gauge_minutes == 30
    assert profile.freshness.flood_sensor_minutes == 90
    assert set(available_region_profiles()) == {"example-region", "minxiong"}


def test_packaged_profile_boundary_is_non_authoritative_geojson():
    profile = load_region_profile("minxiong")

    boundary = load_region_boundary(profile)

    assert boundary["type"] == "FeatureCollection"
    assert boundary["features"][0]["properties"]["region_id"] == "minxiong"
    assert (
        boundary["features"][0]["properties"]["boundary_type"]
        == "operational_working_bounds"
    )


def test_custom_profile_rejects_unknown_fields(tmp_path):
    payload = load_region_profile("minxiong").model_dump(mode="json")
    payload["region"]["unsupported"] = True
    path = tmp_path / "invalid.yaml"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="unsupported"):
        load_region_profile(path)


def test_profile_rejects_non_json_yaml_without_optional_parser(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("region:\n  id: example\n", encoding="utf-8")

    with pytest.raises(ValueError, match="JSON-compatible YAML"):
        load_region_profile(path)
