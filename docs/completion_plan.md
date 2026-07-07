# Completion Plan

FloodCastTW is complete when it can repeatedly build a Taiwan radar/rainfall event dataset,
train and evaluate baselines plus one deep-learning nowcaster, and publish a documented
Chiayi/Minxiong-ready model without committing credentials, raw official data, or model weights.

## Definition Of Done

- CWA radar/QPE and WRA/NCDR auxiliary ingestion runs from documented local configuration.
- Multi-frame CWA radar events can be collected, inspected, converted, and evaluated.
- Event-based train/validation/test splits are populated with real historical weather events.
- A persistence baseline, a small trainable neural baseline, and a SOTA migration candidate are
  evaluated with the same metrics.
- A Minxiong/Chiayi model card documents data sources, limitations, metrics, and attribution.
- CI covers unit tests, linting, and dry-run contract checks.
- Raw data, API keys, checkpoints, and generated artifacts remain outside git.

## Current Status

- Completed: CWA `O-A0059-001` historyAPI live verification, short multi-frame radar sequence
  download, sequence validation, XML/JSON CWA grid parsing, tensor conversion, and persistence
  baseline evaluation on a real CWA radar tensor.
- Completed: optional Tiny U-Net training entrypoint with deterministic seed, checkpoint save, and
  resume support.
- Completed: Tiny U-Net 2-GPU smoke training on the target server with two visible RTX 4090 GPUs.
- Completed: CWA nodata masking and z-score normalization for baseline evaluation and Tiny U-Net
  smoke training.
- Completed: baseline model card for Minxiong/Chiayi-oriented smoke testing.
- Completed: local WRA API key configuration; real key stays in ignored `.env`.
- Pending integration work: WRA official API endpoint contracts still need implementation in the
  ingestion layer.
- Pending training work: collect enough event windows for meaningful Tiny U-Net or NowcastNet
  training.
- Pending benchmark work: collect real Chiayi/Minxiong heavy-rain and Taiwan-wide typhoon/front
  event windows before reporting model performance.

## Phase 1: Data Source Finalization

- Live-verify CWA historyAPI endpoint and retention for `O-A0059-001`.
- Download a short multi-frame radar sequence under `data/external/radar/`.
- Extend event planning from file-list selection to actual frame download.
- Add schema checks for every frame in a sequence: timestamp spacing, grid consistency, units, and
  nodata encoding.
- Confirm WRA API/access once the WRA application is approved.

## Phase 2: Dataset Build

- Build a CWA radar event collector that writes ignored raw frames and tracked summaries.
- Populate `data/samples/event_split_manifest.json` with real historical events.
- Add event manifests for Chiayi/Minxiong heavy-rain windows and Taiwan-wide typhoon/front events.
- Add gauge/QPE validation reports so QPE is not treated as ground truth without checks.
- Produce reproducible dataset summaries under `data/processed/run_summaries/`.

## Phase 3: Tensor Conversion

- Implement the production CWA `O-A0059-001` adapter.
- Convert event frame sequences into fixed tensor archives.
- Preserve CRS, origin, resolution, nodata values, and data timestamps in tensor metadata.
- Add regression tests using tiny synthetic CWA-like fixtures, not official raw data.

## Phase 4: Modeling

- Evaluate persistence on real converted radar events.
- Train a small ConvLSTM or U-Net on one RTX 4090 first.
- Add checkpoint save/resume and deterministic run summaries.
- Compare CSI, POD, FAR, RMSE, and lead-time metrics across baselines.
- Migrate NowcastNet only after its code/checkpoint license and tensor contract are reviewed.

## Phase 5: Local Flood-Risk Layer

- Align radar/QPE, gauges, flood sensors, shelters, and risk areas to shared spatial references.
- Add Minxiong/Chiayi feature tables for recent rainfall, QPE accumulation, sensor status, and
  township/village context.
- Evaluate `RainfallThresholdRiskScorer`, then add LightGBM/XGBoost only after labels are ready.

## Phase 6: Release And Operations

- Publish model cards for Taiwan-wide and Minxiong/Chiayi-specific checkpoints.
- Add scheduled jobs only after manual ingestion and validation are repeatable.
- Add alerting only after run summaries expose reliable failure reasons.
- Keep deployment configuration separate from research/training artifacts.
