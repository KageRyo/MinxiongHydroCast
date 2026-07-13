# Minxiong/Chiayi Baseline Model Card

## Model

- Name: MinxiongHydroCast persistence baseline
- Model type: `PersistenceNowcaster`
- Task: radar echo nowcasting smoke baseline
- Intended region: Taiwan-wide radar grid, with downstream checks for Chiayi County and Minxiong

## Data Sources

- CWA `O-A0059-001` radar echo history sample.
- Live-verified sample window: `2026-07-07T08:40:00+08:00` to
  `2026-07-07T09:00:00+08:00`.
- Local raw frames are stored under ignored `data/external/` paths and are not committed.
- Tensor archive metadata preserves `dBZ`, `TWD67`, 10-minute cadence, grid origin, resolution,
  nodata values, and source timestamps.

## Evaluation

The current results are pipeline smoke tests, not scientific performance claims.

- Input shape: `2 x 881 x 921 x 1`
- Target shape: `1 x 881 x 921 x 1`
- Event threshold: `35.0 dBZ`
- Valid pixels: `1946`
- Ignored nodata pixels: `809455`
- RMSE: `11.676495 dBZ`
- CSI: `0.302741`
- POD: `0.455197`
- FAR: `0.525234`

Tiny U-Net training infrastructure smoke result:

- Device: two RTX 4090 GPUs through PyTorch `DataParallel`
- Batch repeats: 2
- Epochs: 1
- Normalization: z-score over valid input/target pixels
- Final masked loss: `0.997039`
- Checkpoint: ignored local path under `data/external/checkpoints/`

Tiny U-Net versus persistence smoke comparison on the same valid pixels:

- Persistence RMSE/CSI/POD/FAR: `11.676495`, `0.302741`, `0.455197`, `0.525234`
- Tiny U-Net RMSE/CSI/POD/FAR: `10.878726`, `0.0`, `0.0`, `0.0`
- Interpretation: the smoke checkpoint improves RMSE but fails event detection at `35 dBZ`.

## Limitations

- This baseline repeats the latest frame and has no learned dynamics.
- The sample is too short for training or benchmark reporting.
- Radar echo is not the same as surface rainfall or flood depth.
- The neural-training smoke run masks CWA nodata values, but the dataset is far too short for
  model selection.
- Minxiong flood-risk evaluation still requires labels, local gauges, sensors, and QPE/gauge
  validation.

## Use

Use this baseline to verify ingestion, tensor conversion, metrics, and run summaries before
training ConvLSTM/U-Net or migrating NowcastNet.
