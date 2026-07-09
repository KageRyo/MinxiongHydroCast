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

## Full CWA Event Lead-Time Baselines

The first longer CWA benchmark uses three complete `O-A0059-001` 10-minute radar windows. Each
archive uses 6 input frames and predicts 6 lead frames, so lead-time metrics cover 10 to 60
minutes. The Taiwan-wide event is used for Tiny U-Net training; the two Chiayi/Minxiong events are
local test windows.

| Event | Split | Windows | Persistence RMSE | Persistence CSI | Tiny U-Net RMSE | Tiny U-Net CSI | Weighted Tiny U-Net RMSE | Weighted Tiny U-Net CSI |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Taiwan-wide 2026-06-28 | train | 38 | `8.311872` | `0.214701` | `8.100073` | `0.048339` | `6.820217` | `0.210941` |
| Chiayi/Minxiong 2026-07-02 | test | 26 | `11.465393` | `0.278248` | `9.914263` | `0.086701` | `9.564780` | `0.246535` |
| Chiayi/Minxiong 2026-07-03 | test | 26 | `10.421478` | `0.315475` | `9.496191` | `0.121837` | `8.719508` | `0.286868` |

Persistence lead-time CSI drops as horizon increases. On the Taiwan-wide train event it moves from
`0.347882` at 10 minutes to `0.148771` at 60 minutes. On the two Chiayi/Minxiong test events it
moves from `0.424883` to `0.164930`, and from `0.477052` to `0.221392`.

The first 1-epoch Tiny U-Net/RainNet-style baseline used the CUDA-enabled `VLM` environment, two
RTX 4090 GPUs via `DataParallel`, `hidden_channels=8`, and `batch_size=2`. It lowers aggregate
RMSE but has much worse CSI than persistence.

The weighted Tiny U-Net run used `--loss-function weighted_mse`, `--event-threshold 35`,
`--event-weight 4`, `--validation-fraction 0.2`, 20 epochs, and the same two RTX 4090 GPUs. It
improves RMSE and recovers much of the CSI gap, but persistence still has better CSI on all three
events. Keep persistence as the primary benchmark until more event diversity is available.

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
