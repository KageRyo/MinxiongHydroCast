# Radar Tensor Conversion

FloodCastTW uses a tiny tracked radar-like fixture to test model tensor I/O before real radar
archives are confirmed. This is a dry-run format, not a claim about CWA native radar files.

## Fixture

The fixture is `data/samples/radar_pixels.csv`. It stores one demo event as pixel rows:

- `event_id`
- `frame_index`
- `y`
- `x`
- `mm_per_hour`

The sample has five `2 x 2` frames. With `input_length=3` and `prediction_length=2`, it becomes:

- `input`: `[3, 2, 2, 1]`
- `target`: `[2, 2, 2, 1]`

## Convert

```bash
floodcasttw-radar-tensor-convert \
  --source-format csv_pixel_grid \
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

The output `.npz` archive contains:

- `input`: model input tensor
- `target`: future rainfall tensor
- `spec`: JSON-encoded `RadarTensorSpec`
- `metadata`: JSON-encoded event/source metadata

The command writes the standard run summary and JSONL run log.
Source adapters are documented in [radar_source_adapters.md](radar_source_adapters.md).

## Evaluate

Run the persistence baseline against the generated archive:

```bash
floodcasttw-tensor-baseline-evaluate \
  --archive data/processed/radar_tensor_sample.npz \
  --output data/processed/tensor_baseline_evaluation.json
```

This reports RMSE plus CSI/POD/FAR at the selected event threshold. Use it as the baseline before
testing ConvLSTM, U-Net, or NowcastNet-style models on the same tensor contract.

## Production Path

After the radar source manifest is confirmed, replace the CSV fixture reader with a source-specific
reader for the native archive format. Keep the tensor archive contract stable so baselines,
NowcastNet adapters, and future training code can share the same I/O.

For CWA, use `O-A0059-001` first. A sample downloaded on 2026-07-06 confirmed a `921 x 881`
TWD67 lon/lat grid with 0.0125 degree resolution, lower-left origin `115.0E, 18.0N`, west-to-east
then south-to-north value ordering, `dBZ` units, and nodata values `-99` and `-999`. The production
converter should fail if any frame disagrees on cadence, grid shape, extent, units, nodata encoding,
or timestamp ordering.

Keep `O-B0045-001` available as a rainfall-estimate grid candidate for flood-risk features or
secondary targets. Its sample confirmed a `441 x 561` TWD67 lon/lat grid, lower-left origin
`118.0E, 20.0N`, `mm` units, and nodata `-1`.
