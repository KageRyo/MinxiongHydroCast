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
- [x] Add a CWA radar event summary command for Minxiong/Chiayi local and Taiwan-wide threshold
      evidence.
- [x] Identify Chiayi/Minxiong heavy-rain and Taiwan-wide widespread radar candidate windows from
      a 240-frame CWA hourly discovery scan.
- [x] Download complete 10-minute CWA sequences for the selected candidate windows.
- [x] Convert complete CWA event windows into 6-input/6-output sliding tensor archives.
- [x] Add lead-time metric breakdowns for sliding-window tensor archives.
- [x] Train and evaluate the Tiny U-Net/RainNet-style baseline on full CWA event windows.
- [x] Define a NowcastNet readiness gate so SOTA migration waits for stable data and license
      review.

## Next

### Phase 1: Data Source Finalization

- [x] Confirm local WRA API key storage without committing the key.
- [ ] Implement WRA official API ingestion after endpoint contracts are confirmed.

### Phase 2: Dataset Build

- [x] Track Chiayi/Minxiong heavy-rain and Taiwan-wide widespread radar candidate windows in
      `data/samples/radar_event_windows.json`.
- [ ] Attach official CWA weather context before labeling Taiwan-wide windows as typhoon or
      frontal events.
- [x] Add a tracked event weather-context manifest so radar-only windows cannot be mislabeled as
      typhoon, Mei-yu, or frontal before official CWA evidence is attached.
- [x] Add a CWA official weather-context source review manifest with reviewed pages, current
      coverage, and next historical chart probe URLs.
- [x] Probe candidate event-time CWA historical `SFCcombo` chart URLs.
- [ ] Find another official CWA event-time source and assign official weather-type labels; the
      candidate `SFCcombo` URLs returned HTTP 404.
- [x] Add a QPE/gauge validation report command so QPE is treated as an estimate, not direct
      ground truth.
- [x] Add a direct CWA history `getData` downloader for event-time rain-gauge captures and QPE
      availability probes.
- [x] Parse CWA `O-A0002-001` XML rain-gauge captures in the QPE/gauge validator.
- [x] Record per-event QPE/gauge validation availability in
      `data/samples/qpe_gauge_validation_status.json`.
- [ ] Run live QPE/gauge validation reports for each selected event after event-time
      `O-B0045-001` QPE grids are captured or an official historical QPE archive is confirmed.
- [ ] Produce reproducible dataset summaries under ignored `data/processed/run_summaries/`.
- [x] Add a next-batch event expansion queue from the existing CWA hourly discovery scan.
- [ ] Add more train events across typhoon, frontal, Mei-yu, and convective regimes before SOTA
      model migration.

### Phase 3: Tensor Conversion

- [x] Build a production CWA radar tensor converter once the source format is confirmed.
- [x] Add a production CWA radar source adapter once native format is confirmed.
- [x] Convert event frame sequences into fixed tensor archives.
- [x] Convert longer event frame sequences into sliding-window tensor archives.
- [x] Preserve CRS, origin, resolution, nodata values, units, and timestamps in tensor metadata.
- [x] Add regression tests using synthetic CWA-like fixtures instead of official raw data.

### Phase 4: Modeling

- [x] Evaluate persistence on real converted radar event tensors.
- [x] Add a small U-Net training entrypoint for one RTX 4090 before using both GPUs.
- [x] Add checkpoint save/resume and deterministic training run summaries.
- [x] Use the CUDA-enabled `VLM` environment and run the Tiny U-Net baseline on two GPUs.
- [x] Mask CWA nodata values and normalize radar tensors before neural smoke training.
- [x] Compare CSI, POD, FAR, and RMSE across persistence and Tiny U-Net smoke outputs.
- [x] Add lead-time metric breakdowns after collecting longer multi-step event windows.
- [x] Add threshold-weighted Tiny U-Net loss options, validation split support, and early stopping
      metadata for stronger-event experiments.
- [x] Run the weighted Tiny U-Net experiment on two RTX 4090 GPUs and compare full-event metrics.
- [ ] Wire NowcastNet inference only after event diversity, code, checkpoint, tensor shape, and
      license are reviewed.

### Phase 5: Local Flood-Risk Layer

- [ ] Align radar/QPE, gauges, flood sensors, shelters, and risk areas to shared spatial
      references.
- [ ] Add Minxiong/Chiayi feature tables for rainfall, QPE accumulation, sensor status, and
      township/village context.
- [ ] Evaluate `RainfallThresholdRiskScorer` on real event windows.
- [ ] Add LightGBM/XGBoost only after labels and feature tables are stable.

### Phase 6: Release And Operations

- [ ] Publish model cards for Taiwan-wide and Minxiong/Chiayi-specific checkpoints.
- [x] Add locked one-shot and interval scheduling for rainfall-alert and hydrology ingestion.
- [x] Add immutable checksummed snapshots, latest pointers, retention, and failed-attempt records.
- [x] Add freshness/schema/readiness health checks and a versioned read API.
- [x] Add a localhost operator view separating official-source data and experimental forecasts.
- [x] Add systemd collector timer and API supervision templates for Linux deployment.
- [x] Add a shadow-history report with heavy-rain evidence and an explicit notification blocker.
- [ ] Add a durable remote-storage backend, process supervision, metrics export, and backups.
- [ ] Route failed/stale/schema alerts after deployment owners and channels are assigned.
- [ ] Keep deployment configuration separate from research/training artifacts.

## Later

- [ ] Move selected stable workflows from manual commands to scheduled automation.
- [ ] Add a lightweight dashboard only after ingestion, validation, and model outputs are stable.
