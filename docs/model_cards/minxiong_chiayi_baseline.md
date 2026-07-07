# Minxiong/Chiayi Baseline Model Card

## Model

- Name: FloodCastTW persistence baseline
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

The current result is a pipeline smoke test, not a scientific performance claim.

- Input shape: `2 x 881 x 921 x 1`
- Target shape: `1 x 881 x 921 x 1`
- Event threshold: `35.0 dBZ`
- RMSE: `6.582019 dBZ`
- CSI: `0.237828`
- POD: `0.38081`
- FAR: `0.612214`

## Limitations

- This baseline repeats the latest frame and has no learned dynamics.
- The sample is too short for training or benchmark reporting.
- Radar echo is not the same as surface rainfall or flood depth.
- Minxiong flood-risk evaluation still requires labels, local gauges, sensors, and QPE/gauge
  validation.

## Use

Use this baseline to verify ingestion, tensor conversion, metrics, and run summaries before
training ConvLSTM/U-Net or migrating NowcastNet.
