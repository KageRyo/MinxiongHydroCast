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

## Convert CWA Event Collections

The CWA history `getData` endpoint currently returns XML for `O-A0059-001`, while the file API
sample returns JSON. The `cwa_opendata_grid` adapter accepts both formats and can read a collection
manifest produced by `floodcasttw-cwa-event-plan --download`.

```bash
floodcasttw-radar-tensor-convert \
  --source-format cwa_opendata_grid \
  --input data/processed/cwa_event_collection.json \
  --event-id cwa_o_a0059_recent_sample_20260707 \
  --input-length 2 \
  --prediction-length 1 \
  --cadence-minutes 10 \
  --output data/processed/cwa_recent_tensor_sample.npz
```

The adapter validates sequence cadence and grid consistency before writing tensors. Tensor metadata
keeps CWA data ID, timestamps, source paths, origin, resolution, nodata values, units, and CRS.

## Evaluate

Run the persistence baseline against the generated archive:

```bash
floodcasttw-tensor-baseline-evaluate \
  --archive data/processed/radar_tensor_sample.npz \
  --output data/processed/tensor_baseline_evaluation.json
```

This reports RMSE plus CSI/POD/FAR at the selected event threshold. Use it as the baseline before
testing ConvLSTM, U-Net, or NowcastNet-style models on the same tensor contract.

## Live CWA Smoke Result

A live CWA historyAPI sample collected on 2026-07-07 validated the first real end-to-end radar
path:

- Source: `O-A0059-001`
- Frames: 3
- Window: `2026-07-07T08:40:00+08:00` to `2026-07-07T09:00:00+08:00`
- Tensor input: `2 x 881 x 921 x 1`
- Tensor target: `1 x 881 x 921 x 1`
- Units/CRS: `dBZ`, `TWD67`
- Cadence: 10 minutes

The persistence smoke baseline at a `35.0 dBZ` event threshold ignores CWA nodata values `-999`
and `-99`. It used 1,946 valid pixels, ignored 809,455 nodata pixels, and produced RMSE
`11.676495 dBZ`, CSI `0.302741`, POD `0.455197`, and FAR `0.525234`. This is a pipeline
verification result, not a scientific benchmark.

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
