# Model Strategy

FloodCastTW should not start with a deep-learning model. The project first needs stable live data,
radar grids, labels, and repeatable validation. The recommended model path is staged.

## Best First Model

Use `PersistenceNowcaster` as the first rainfall nowcasting baseline. It repeats the latest radar
or gridded rainfall frame across the forecast horizon. It is simple, hard to beat on short horizons,
and gives a clean benchmark before trying SOTA models.

For flood risk, start with `RainfallThresholdRiskScorer`, then move to LightGBM or XGBoost after
historical flood labels and features are available.

## SOTA Candidate

The old project contained a NowcastNet-style research capsule. NowcastNet is a strong SOTA
candidate for extreme precipitation nowcasting, but it is not ready to run here until these are
available:

- Taiwan radar tensors aligned to a fixed grid.
- Train/validation/test splits by weather event, not random rows.
- GPU environment and model checkpoints.
- Evaluation metrics such as CSI, POD, FAR, RMSE, and lead-time breakdowns.
- License notices for any third-party code copied into this repository.

The current code provides `NowcastNetAdapter` as the integration boundary. Do not commit the old
zip, external datasets, or checkpoints directly to git.

## Recommended Roadmap

1. Stabilize WRA/CWA/NCDR ingestion and validation.
2. Build a grid-alignment pipeline for radar, gauges, sensors, shelters, and flood-risk areas.
3. Run persistence and threshold baselines.
4. Add LightGBM for local flood-risk classification.
5. Migrate NowcastNet only after radar data and checkpoint strategy are clear.

For Minxiong, train or calibrate locally on top of a wider Chiayi/Taiwan dataset. A Minxiong-only
deep model will likely overfit because extreme events are sparse.
