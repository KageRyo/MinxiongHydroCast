"""Regular WGS84 grid definitions for radar and model outputs."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor


@dataclass(frozen=True)
class GridSpec:
    name: str
    west: float
    south: float
    east: float
    north: float
    resolution_degrees: float
    crs: str = "EPSG:4326"

    @property
    def rows(self) -> int:
        return ceil((self.north - self.south) / self.resolution_degrees)

    @property
    def cols(self) -> int:
        return ceil((self.east - self.west) / self.resolution_degrees)

    def contains(self, latitude: float, longitude: float) -> bool:
        return self.south <= latitude <= self.north and self.west <= longitude <= self.east

    def cell_index(self, latitude: float, longitude: float) -> tuple[int, int]:
        if not self.contains(latitude, longitude):
            raise ValueError(f"point outside grid {self.name}: {latitude}, {longitude}")
        row = floor((self.north - latitude) / self.resolution_degrees)
        col = floor((longitude - self.west) / self.resolution_degrees)
        return min(row, self.rows - 1), min(col, self.cols - 1)

    def cell_id(self, latitude: float, longitude: float) -> str:
        row, col = self.cell_index(latitude, longitude)
        return f"{self.name}:r{row:04d}:c{col:04d}"


CHIAYI_COUNTY_GRID = GridSpec(
    name="chiayi_county_wgs84_0p01",
    west=120.10,
    south=23.20,
    east=120.95,
    north=23.65,
    resolution_degrees=0.01,
)

MINXIONG_GRID = GridSpec(
    name="minxiong_wgs84_0p005",
    west=120.38,
    south=23.48,
    east=120.52,
    north=23.62,
    resolution_degrees=0.005,
)
