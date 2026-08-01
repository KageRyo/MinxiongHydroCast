"""Strict, packageable region-profile contracts."""

from __future__ import annotations

import json
import re
from importlib import resources
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

PROFILE_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProfileSection(BaseModel):
    """Base model for fail-closed region-profile sections."""

    model_config = ConfigDict(extra="forbid", strict=True)


class RegionIdentity(ProfileSection):
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1)
    county: str = Field(min_length=1)
    county_code: str = Field(pattern=r"^\d{5}$")
    township: str = Field(min_length=1)
    township_code: str = Field(pattern=r"^\d{8}$")
    timezone: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> RegionIdentity:
        if not self.township_code.startswith(self.county_code):
            raise ValueError("township_code must belong to county_code")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {self.timezone}") from exc
        return self


class CoverageContract(ProfileSection):
    required_rain_gauges: int = Field(ge=0)
    required_flood_sensors: int = Field(ge=0)


class SpatialContract(ProfileSection):
    boundary_file: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*\.geojson$")
    radar_grid_contract: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._-]*$")


class FreshnessContract(ProfileSection):
    rain_gauge_minutes: float = Field(gt=0)
    flood_sensor_minutes: float = Field(gt=0)


class RegionProfile(ProfileSection):
    """Operational boundary, coverage, spatial, and freshness configuration."""

    schema_version: Literal[1] = 1
    region: RegionIdentity
    coverage: CoverageContract
    spatial: SpatialContract
    freshness: FreshnessContract


def _packaged_profile_text(profile_id: str) -> str:
    if not PROFILE_ID.fullmatch(profile_id):
        raise ValueError(f"invalid region profile id: {profile_id}")
    resource = resources.files("minxionghydrocast").joinpath(
        "profiles",
        f"{profile_id}.yaml",
    )
    if not resource.is_file():
        available = ", ".join(available_region_profiles()) or "none"
        raise FileNotFoundError(
            f"unknown region profile '{profile_id}'; available profiles: {available}"
        )
    return resource.read_text(encoding="utf-8")


def available_region_profiles() -> list[str]:
    root = resources.files("minxionghydrocast").joinpath("profiles")
    return sorted(
        item.name.removesuffix(".yaml")
        for item in root.iterdir()
        if item.is_file() and item.name.endswith(".yaml")
    )


def load_region_profile(reference: str | Path = "minxiong") -> RegionProfile:
    """Load a packaged profile ID or a JSON-compatible YAML profile path.

    JSON is a strict subset of YAML. Keeping tracked profiles in this subset lets the base wheel
    load and validate them without adding a YAML parser to the runtime dependency set.
    """

    path = Path(reference)
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        source = str(path)
    else:
        text = _packaged_profile_text(str(reference))
        source = f"packaged profile {reference}"
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{source} must use JSON-compatible YAML: {exc.msg} at line {exc.lineno}"
        ) from exc
    return RegionProfile.model_validate(payload)


def load_region_boundary(profile: RegionProfile) -> dict[str, object]:
    """Load and minimally validate the packaged GeoJSON boundary for a profile."""

    resource = resources.files("minxionghydrocast").joinpath(
        "profiles",
        "boundaries",
        profile.spatial.boundary_file,
    )
    if not resource.is_file():
        raise FileNotFoundError(
            f"boundary file not packaged: {profile.spatial.boundary_file}"
        )
    try:
        payload = json.loads(resource.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid boundary GeoJSON {profile.spatial.boundary_file}: {exc.msg}"
        ) from exc
    if payload.get("type") != "FeatureCollection":
        raise ValueError("region boundary must be a GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("region boundary must contain at least one feature")
    return payload
