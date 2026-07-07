# Radar Source Adapters

Radar source adapters isolate source-specific file reading from the model tensor contract. The
converter should emit the same `.npz` archive regardless of whether the input came from a tiny CSV
fixture, CWA/QPESUMS archives, or another confirmed radar source.

## Current Adapters

`csv_pixel_grid` reads `data/samples/radar_pixels.csv`, validates required fields, builds a
`[time, height, width, channels]` sequence, and passes that sequence to the tensor conversion
pipeline.

```bash
floodcasttw-radar-tensor-convert \
  --source-format csv_pixel_grid \
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

`cwa_opendata_grid` reads CWA Open Data grid JSON/XML files or a collection manifest produced by
`floodcasttw-cwa-event-plan --download`. It validates cadence, grid consistency, CRS, units,
timestamps, and nodata encoding before emitting the tensor archive.

```bash
floodcasttw-radar-tensor-convert \
  --source-format cwa_opendata_grid \
  --input data/processed/cwa_event_collection.json \
  --input-length 2 \
  --prediction-length 1 \
  --cadence-minutes 10 \
  --output data/processed/cwa_recent_tensor_sample.npz
```

## Adding A Production Adapter

The first production adapter targets CWA `O-A0059-001`. A second adapter or mode can target CWA
`O-B0045-001` for past-1-hour QPESUMS rainfall estimate grids.

Add a new adapter only after the radar source manifest is confirmed. A production adapter should:

- read the native source format without committing raw files
- load files from ignored paths such as `data/external/radar/cwa_o_a0059_001/`
- validate cadence, units, projection, and grid metadata
- verify origin, extent, orientation, timestamp timezone, and missing-value encoding
- emit a full sequence matching `RadarTensorSpec`
- preserve event/source metadata in the tensor archive
- fail loudly on missing frames, duplicate pixels, or incompatible grids

Do not read `CWA_API_KEY` inside the adapter. Downloading belongs in `floodcasttw-cwa-download` or
`floodcasttw-cwa-event-plan --download`; the adapter consumes already downloaded local files and
redacted manifests.
