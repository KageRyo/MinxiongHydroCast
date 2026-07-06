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

Add a new adapter only after the radar source manifest is confirmed. A production adapter should:

- read the native source format without committing raw files
- validate cadence, units, projection, and grid metadata
- emit a full sequence matching `RadarTensorSpec`
- preserve event/source metadata in the tensor archive
- fail loudly on missing frames, duplicate pixels, or incompatible grids

Keep production radar files under ignored paths such as `data/external/`.
