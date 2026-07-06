# Radar Source Adapters

Radar source adapters isolate source-specific file reading from the model tensor contract. The
converter should emit the same `.npz` archive regardless of whether the input came from a tiny CSV
fixture, CWA/QPESUMS archives, or another confirmed radar source.

## Current Adapter

`csv_pixel_grid` is the only supported adapter today. It reads `data/samples/radar_pixels.csv`,
validates required fields, builds a `[time, height, width, channels]` sequence, and passes that
sequence to the tensor conversion pipeline.

```bash
floodcasttw-radar-tensor-convert \
  --source-format csv_pixel_grid \
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

## Adding A Production Adapter

The first production adapter should target CWA `O-A0059-001` after sample files confirm the native
schema. A second adapter or mode can target CWA `O-B0045-001` for past-1-hour QPESUMS rainfall
estimate grids.

Add a new adapter only after the radar source manifest is confirmed. A production adapter should:

- read the native source format without committing raw files
- load files from ignored paths such as `data/external/radar/cwa_o_a0059_001/`
- validate cadence, units, projection, and grid metadata
- verify origin, extent, orientation, timestamp timezone, and missing-value encoding
- emit a full sequence matching `RadarTensorSpec`
- preserve event/source metadata in the tensor archive
- fail loudly on missing frames, duplicate pixels, or incompatible grids

Do not read `CWA_API_KEY` inside the adapter. Downloading belongs in a separate ingestion command;
the adapter should consume already downloaded local files.
