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

See [nowcastnet_migration.md](nowcastnet_migration.md) for the radar tensor contract and smoke
test workflow. See [event_splits.md](event_splits.md) for event-based train/validation/test
rules.

## GPU Training Environment

The target server has two RTX 4090 GPUs with 24 GB VRAM each and NVIDIA driver `570.133.07`.
This is enough to test modern radar nowcasting models after the data pipeline is stable. Use the
GPUs first for controlled experiments:

- Run persistence and threshold baselines on CPU.
- Evaluate tensor archives with `floodcasttw-tensor-baseline-evaluate` before deep learning.
- Create a separate training environment with CUDA-enabled PyTorch.
- Run a small ConvLSTM or U-Net nowcasting baseline on one GPU first.
- Use both GPUs only after data loading, checkpointing, and evaluation are repeatable.
- Reserve NowcastNet-style training for gridded Taiwan radar tensors with event-based splits.

## Recommended Roadmap

1. Stabilize WRA/CWA/NCDR ingestion and validation.
2. Build a grid-alignment pipeline for radar, gauges, sensors, shelters, and flood-risk areas.
3. Define event-based train/validation/test splits.
4. Convert radar-like inputs into stable tensor archives.
5. Run persistence and threshold baselines.
6. Add LightGBM for local flood-risk classification.
7. Migrate NowcastNet only after radar data and checkpoint strategy are clear.

For Minxiong, train or calibrate locally on top of a wider Chiayi/Taiwan dataset. A Minxiong-only
deep model will likely overfit because extreme events are sparse.
