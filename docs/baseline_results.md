# Baseline Results

These results are demo-safe smoke-test results from `data/samples/flood_risk_events.csv` and a
small synthetic radar-like nowcasting case. They are not scientific model performance claims.

Run:

```bash
floodcasttw-evaluate-baselines \
  --events data/samples/flood_risk_events.csv \
  --output data/processed/baseline_evaluation.json
```

## Persistence Nowcasting

- Model: `PersistenceNowcaster`
- Horizon: 3 lead steps
- Input shape: `3 x 2 x 2`
- Target shape: `3 x 2 x 2`
- RMSE: `4.041452 mm`
- Event threshold: `10.0 mm`
- CSI: `0.5`
- POD: `0.5`
- FAR: `0.0`

## Tensor Archive Baseline

Run after creating `data/processed/radar_tensor_sample.npz` with
`floodcasttw-radar-tensor-convert`:

```bash
floodcasttw-tensor-baseline-evaluate \
  --archive data/processed/radar_tensor_sample.npz \
  --output data/processed/tensor_baseline_evaluation.json
```

The tensor archive path evaluates the same persistence idea on the model I/O contract used by
future SOTA adapters:

- Input shape: `3 x 2 x 2 x 1`
- Target shape: `2 x 2 x 2 x 1`
- Event threshold: `10.0 mm`
- RMSE: `2.95804 mm`
- CSI: `0.5`
- POD: `0.5`
- FAR: `0.0`

## Live CWA Radar Smoke Baseline

Run after collecting a CWA `O-A0059-001` event sequence and converting it with
`--source-format cwa_opendata_grid`:

```bash
floodcasttw-tensor-baseline-evaluate \
  --archive data/processed/cwa_recent_tensor_sample.npz \
  --output data/processed/cwa_recent_tensor_baseline_evaluation.json \
  --event-threshold-mm 35
```

The option name is retained for compatibility, but for `O-A0059-001` the threshold units are
`dBZ`, not millimeters.

- Source window: `2026-07-07T08:40:00+08:00` to `2026-07-07T09:00:00+08:00`
- Input shape: `2 x 881 x 921 x 1`
- Target shape: `1 x 881 x 921 x 1`
- Units/CRS: `dBZ`, `TWD67`
- Event threshold: `35.0 dBZ`
- Valid pixels: `1946`
- Ignored nodata pixels: `809455`
- Nodata values: `-999`, `-99`
- RMSE: `11.676495 dBZ`
- CSI: `0.302741`
- POD: `0.455197`
- FAR: `0.525234`

This live result verifies the pipeline on real CWA history data. It is too short for model
selection or scientific reporting.

## Tiny U-Net 2-GPU Smoke Training

The Tiny U-Net training entrypoint was smoke-tested on the target server with two RTX 4090 GPUs
visible through PyTorch `DataParallel`.

- Environment: `VLM`
- Device: `cuda`
- CUDA devices used: 2
- GPU names: `NVIDIA GeForce RTX 4090`, `NVIDIA GeForce RTX 4090`
- Source archive: `data/processed/cwa_recent_tensor_sample.npz`
- Batch repeats: 2
- Epochs: 1
- Hidden channels: 2
- Normalization: z-score over valid input/target pixels
- Valid target pixels: `6600`
- Ignored target nodata pixels: `1616202`
- Final masked loss: `0.997039`
- Checkpoint path: ignored `data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke/`

This confirms the training loop, checkpoint write, run summary, multi-GPU visibility, nodata
masking, and training normalization. It is still a smoke test rather than a benchmark.

## Tiny U-Net Versus Persistence Smoke Comparison

Run:

```bash
floodcasttw-torch-baseline-evaluate \
  --archive data/processed/cwa_recent_tensor_sample.npz \
  --checkpoint data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke/tiny_unet_nowcaster.pt \
  --event-threshold 35 \
  --output data/processed/tiny_unet_cwa_comparison.json
```

Both models are scored on the same 1,946 valid pixels after applying the CWA nodata mask and the
latest-input validity mask.

| Model | RMSE dBZ | CSI | POD | FAR |
| --- | ---: | ---: | ---: | ---: |
| PersistenceNowcaster | `11.676495` | `0.302741` | `0.455197` | `0.525234` |
| TinyUNetNowcaster | `10.878726` | `0.0` | `0.0` | `0.0` |

The Tiny U-Net smoke checkpoint lowers RMSE by `0.797769 dBZ` but predicts no threshold events at
`35 dBZ`. Do not treat it as a usable model until trained on longer event splits.

## Threshold Flood Risk

- Model: `RainfallThresholdRiskScorer`
- Demo events: 5
- CSI: `0.333333`
- POD: `0.5`
- FAR: `0.5`
- Hits: 1
- Misses: 1
- False alarms: 1
- Correct negatives: 2

## Interpretation

Persistence is the first nowcasting benchmark because it is simple and often hard to beat at short
lead times. The threshold scorer is intentionally basic; it gives a transparent flood-risk baseline
before adding LightGBM, ConvLSTM, U-Net, or NowcastNet-style models.
