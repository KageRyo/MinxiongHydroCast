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
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

The output `.npz` archive contains:

- `input`: model input tensor
- `target`: future rainfall tensor
- `spec`: JSON-encoded `RadarTensorSpec`
- `metadata`: JSON-encoded event/source metadata

The command writes the standard run summary and JSONL run log.

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
