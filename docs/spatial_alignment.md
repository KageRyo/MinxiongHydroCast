# Spatial Alignment

FloodCastMinxiong aligns observations and risk assets through a common location reference table and
regular WGS84 grids.

## Location Reference

Build a reference table from processed hydrology outputs:

```bash
floodcast-minxiong-locations \
  --rain data/processed/rain_monitor.csv \
  --flood data/processed/flood_sensors.csv \
  --output data/processed/location_reference.csv
```

Each row has a stable `location_id`, `source_type`, source name, administrative fields, optional
coordinates, coordinate source, and `admin_unit_key`. The key format is:

```text
county|township|village
```

Village may be empty when the source does not provide it.

## Coordinates

The spatial module keeps original source coordinate columns where available and normalizes usable
coordinates to WGS84 (`EPSG:4326`). TWD97 TM2 zone 121 coordinates can be converted with
`twd97_tm2_to_wgs84`. Coordinates outside Taiwan bounds are treated as missing instead of being
silently accepted.

## Grids

Two starter grids are defined in `src/floodcastminxiong/spatial/grid.py`:

- `CHIAYI_COUNTY_GRID`: 0.01 degree cells for county-scale alignment.
- `MINXIONG_GRID`: 0.005 degree cells for local calibration.

These are design grids, not final scientific grids. Radar migration should replace or refine them
after the radar projection, cadence, and native resolution are confirmed.

## Scaling Assumptions

- Minxiong is the pilot area, but IDs and schemas must work for Taiwan-wide sources.
- Station IDs from official APIs should override generated IDs once stable IDs are available.
- Address-based geocoding should be a separate reviewed step, not hidden inside ingestion.
- Model outputs should carry both grid cell IDs and timestamps so evaluation can join observations.
