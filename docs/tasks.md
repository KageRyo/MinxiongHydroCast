# Task List

This list replaces GitHub issues for now. Keep tasks small enough to finish, test, and push on
`main`. The end-to-end target is defined in [completion_plan.md](completion_plan.md).

## Active

- [x] Add CI for compile, lint, and tests.
- [x] Add NowcastNet adapter smoke test and external asset manifest.
- [x] Emit structured run summaries for every command-line pipeline.
- [x] Add radar source manifest checks before tensor conversion.
- [x] Define train/validation/test split rules by weather event.
- [x] Add a tiny tracked radar-like fixture for model contract tests.
- [x] Add a dry-run radar tensor conversion skeleton.
- [x] Add a radar source adapter interface for tensor conversion.
- [x] Verify the persistence baseline accepts converted tensor fixtures.
- [x] Add a tensor archive baseline evaluation command.
- [x] Identify official CWA radar/QPE candidate data IDs and license URL.
- [x] Implement a CWA file API downloader that reads `CWA_API_KEY` from local environment only.
- [x] Download CWA `O-A0059-001` and `O-B0045-001` sample files with a local API key.
- [x] Confirm CWA radar/QPE CRS, grid origin, shape, nodata encoding, timestamps, and units.
- [x] Add schema inspection tests for CWA `O-A0059-001` and `O-B0045-001` sample captures.
- [x] Add a dry-run CWA history file-list client and event plan skeleton.
- [x] Live-verify CWA historyAPI endpoint and retention for `O-A0059-001`.
- [x] Use live history indexes to build multi-frame CWA radar event plans.
- [x] Download event-plan frames under ignored `data/external/`.
- [x] Add sequence-level CWA checks for timestamp spacing, grid consistency, units, and nodata
      encoding.
- [x] Build a CWA radar event collector that writes ignored raw frames and tracked summaries.
- [x] Add a production CWA `O-A0059-001` radar source adapter for tensor conversion.
- [x] Convert a live CWA event sequence into a fixed tensor archive.
- [x] Evaluate persistence on a real converted CWA radar event tensor.
- [x] Add an optional Tiny U-Net PyTorch training entrypoint with checkpoint save/resume and
      deterministic run summaries.
- [x] Run Tiny U-Net smoke training on two RTX 4090 GPUs with PyTorch `DataParallel`.
- [x] Mask CWA nodata values and z-score normalize tensors for Tiny U-Net smoke training.
- [x] Add `WRA_API_KEY` to local configuration support and `env.example` without committing keys.
- [x] Populate event split manifest with a live-verified historical CWA radar sequence sample.

## Next

### Phase 1: Data Source Finalization

- [x] Confirm local WRA API key storage without committing the key.
- [ ] Implement WRA official API ingestion after endpoint contracts are confirmed.

### Phase 2: Dataset Build

- [ ] Add Chiayi/Minxiong heavy-rain event windows and Taiwan-wide typhoon/front event windows.
- [ ] Add gauge/QPE validation reports so QPE is treated as an estimate, not direct ground truth.
- [ ] Produce reproducible dataset summaries under ignored `data/processed/run_summaries/`.

### Phase 3: Tensor Conversion

- [x] Build a production CWA radar tensor converter once the source format is confirmed.
- [x] Add a production CWA radar source adapter once native format is confirmed.
- [x] Convert event frame sequences into fixed tensor archives.
- [x] Preserve CRS, origin, resolution, nodata values, units, and timestamps in tensor metadata.
- [x] Add regression tests using synthetic CWA-like fixtures instead of official raw data.

### Phase 4: Modeling

- [x] Evaluate persistence on real converted radar event tensors.
- [x] Add a small U-Net training entrypoint for one RTX 4090 before using both GPUs.
- [x] Add checkpoint save/resume and deterministic training run summaries.
- [x] Use the CUDA-enabled `VLM` environment and run the Tiny U-Net baseline on two GPUs.
- [x] Mask CWA nodata values and normalize radar tensors before neural smoke training.
- [x] Compare CSI, POD, FAR, and RMSE across persistence and Tiny U-Net smoke outputs.
- [ ] Add lead-time metric breakdowns after collecting longer multi-step event windows.
- [ ] Wire NowcastNet inference only after code, checkpoint, and license are reviewed.

### Phase 5: Local Flood-Risk Layer

- [ ] Align radar/QPE, gauges, flood sensors, shelters, and risk areas to shared spatial
      references.
- [ ] Add Minxiong/Chiayi feature tables for rainfall, QPE accumulation, sensor status, and
      township/village context.
- [ ] Evaluate `RainfallThresholdRiskScorer` on real event windows.
- [ ] Add LightGBM/XGBoost only after labels and feature tables are stable.

### Phase 6: Release And Operations

- [ ] Publish model cards for Taiwan-wide and Minxiong/Chiayi-specific checkpoints.
- [ ] Add scheduled jobs only after ingestion and validation are repeatable by hand.
- [ ] Add alerting only after run summaries expose reliable failure reasons.
- [ ] Keep deployment configuration separate from research/training artifacts.

## Later

- [ ] Move selected stable workflows from manual commands to scheduled automation.
- [ ] Add a lightweight dashboard only after ingestion, validation, and model outputs are stable.
