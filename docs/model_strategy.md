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

## Best CWA Data To Try First

Use CWA `O-A0059-001` (`雷達資料-雷達整合回波資料`) as the first radar tensor source. A live
sample confirmed a `921 x 881` TWD67 lon/lat grid, 0.0125 degree resolution, 10-minute cadence,
west-to-east then south-to-north ordering, and `dBZ` units. That makes it the best first fit for
radar nowcasting models.

Use CWA `O-B0045-001` (`降雨估計資料-QPESUMS過去1小時定量降雨估計格點資料`) as the first
rainfall-estimate grid candidate for flood-risk features. A live sample confirmed a `441 x 561`
TWD67 lon/lat grid and `mm` units. It should still be validated alongside rain gauge observations
before using it as a target.

The recommended model order after CWA sample validation is:

1. Persistence baseline on `O-A0059-001`.
2. Small U-Net/RainNet-style nowcaster through `floodcasttw-train-torch-baseline` on full
   event-window tensors.
3. NowcastNet-style migration only after event diversity, checkpointing, and evaluation are stable.

## GPU Training Environment

The target server has two RTX 4090 GPUs with 24 GB VRAM each and NVIDIA driver `570.133.07`.
This is enough to test modern radar nowcasting models after the data pipeline is stable. Use the
GPUs first for controlled experiments:

- Run persistence and threshold baselines on CPU.
- Evaluate tensor archives with `floodcasttw-tensor-baseline-evaluate` before deep learning.
- Create a separate training environment with CUDA-enabled PyTorch.
- Run `floodcasttw-train-torch-baseline --device auto` on one GPU first.
- Use both GPUs only after data loading, checkpointing, and evaluation are repeatable.
- Reserve NowcastNet-style training for gridded Taiwan radar tensors with event-based splits.

The current default environment does not install PyTorch. Use a CUDA-compatible PyTorch environment
for GPU jobs; on the target server, the `VLM` conda environment has been verified with two visible
RTX 4090 GPUs. Checkpoints stay under ignored `data/external/checkpoints/` paths.

The Tiny U-Net entrypoint supports a multi-GPU smoke run:

```bash
PYTHONPATH=src conda run -n VLM python -m floodcasttw.pipelines.torch_baseline_training \
  --archive data/processed/cwa_recent_tensor_sample.npz \
  --output-dir data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke \
  --device cuda \
  --multi-gpu \
  --batch-repeats 2 \
  --epochs 1
```

Use this to verify training infrastructure only. The training path masks CWA nodata values and
z-score normalizes valid pixels, but real training still needs longer event-based datasets.
Evaluate a trained smoke checkpoint against persistence with:

```bash
PYTHONPATH=src conda run -n VLM python -m floodcasttw.pipelines.torch_baseline_evaluation \
  --archive data/processed/cwa_recent_tensor_sample.npz \
  --checkpoint data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke/tiny_unet_nowcaster.pt \
  --event-threshold 35 \
  --device cpu \
  --output data/processed/tiny_unet_cwa_comparison.json
```

The current smoke checkpoint lowers RMSE but has CSI/POD/FAR of zero at `35 dBZ`, so it is not a
useful nowcaster yet.

For full-event testing, use 6 input frames and 6 prediction frames with sliding windows. The first
full-event run trained on the Taiwan-wide 2026-06-28 event with two RTX 4090 GPUs:

```bash
PYTHONPATH=src conda run -n VLM python -m floodcasttw.pipelines.torch_baseline_training \
  --archive data/processed/cwa_tensor_taiwan_widespread_20260628_6in_6out.npz \
  --output-dir data/external/checkpoints/tiny_unet_cwa_taiwan_widespread_20260628_6in_6out \
  --device cuda \
  --multi-gpu \
  --hidden-channels 8 \
  --batch-size 2 \
  --epochs 1
```

The full-event Tiny U-Net checkpoint lowers aggregate RMSE against persistence on the current
events, but CSI remains worse. It should be treated as a diagnostic baseline while persistence
remains the primary benchmark.

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
