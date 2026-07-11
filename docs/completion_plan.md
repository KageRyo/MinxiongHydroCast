# Completion Plan

FloodCastMinxiong is production-ready when it can continuously ingest and validate official data,
produce versioned Minxiong risk inputs and nowcasts, expose them through a monitored service, and
publish a documented Minxiong model without committing credentials, raw official data, or model
weights. Building datasets and training models are necessary milestones, but are not by themselves
a production release.

## Definition Of Done

- CWA radar/QPE and WRA/NCDR auxiliary ingestion runs from documented local configuration.
- Multi-frame CWA radar events can be collected, inspected, converted, and evaluated.
- Event-based train/validation/test splits are populated with real historical weather events.
- A persistence baseline, a small trainable neural baseline, and a SOTA migration candidate are
  evaluated with the same metrics.
- A Minxiong/Chiayi model card documents data sources, limitations, metrics, and attribution.
- CI covers unit tests, linting, dry-run contract checks, and production configuration validation.
- A scheduler retries ingestion idempotently and raises alerts for stale, missing, or invalid data.
- Versioned outputs are stored durably and served through an authenticated API or operator surface.
- Service-level objectives cover data freshness, pipeline success, and forecast availability.
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
- Completed: persistence versus Tiny U-Net smoke comparison using the same valid-pixel mask and
  metrics.
- Completed: QPE/gauge validation report CLI for local CWA `O-B0045-001` and `O-A0002-001`
  captures.
- Completed: direct CWA history `getData` downloader for event-time products, plus XML parsing for
  `O-A0002-001` rain-gauge captures.
- Completed: per-event QPE/gauge availability status manifest. CWA `O-A0002-001` gauge captures
  parse for the three selected events, but event-time `O-B0045-001` QPE history probes return HTTP
  404.
- Completed: event weather-context manifest that prevents radar-only windows from being mislabeled
  before official CWA evidence is attached.
- Completed: CWA official weather-context source review manifest listing reviewed CWA pages,
  current coverage, and next historical chart probe URLs.
- Completed: Tiny U-Net threshold-weighted loss options, validation split support, and early
  stopping metadata for the next strong-echo experiment.
- Completed: weighted Tiny U-Net full-event run on two RTX 4090 GPUs; RMSE improved, but CSI still
  trails persistence.
- Completed: baseline model card for Minxiong/Chiayi-oriented smoke testing.
- Completed: local WRA API key configuration; real key stays in ignored `.env`.
- Completed: locked one-shot/interval observation collection, immutable checksummed snapshots,
  retention, last-attempt tracking, dynamic freshness/schema readiness, a versioned read API, and
  a localhost operator view.
- Completed: official CWA `O-A0002-001` operational rain-gauge adapter with strict Pydantic input
  schemas, retry/backoff/rate limiting, WGS84/station identifiers, source provenance, degraded
  scraper fallback, and a scheduled credential-safe live contract smoke test.
- Pending deployment work: durable remote storage, process supervision, metrics export,
  authentication, backups, and alert routing to named maintainers.
- Pending integration work: WRA official API endpoint contracts for rainfall alerts and flood
  sensors still need implementation in the ingestion layer.
- Pending official-label work: attach CWA weather maps, warnings, daily reports, or equivalent
  official source evidence to each selected event before weather-type stratification.
- Pending source-search work: candidate event-time CWA historical `SFCcombo` chart URLs were
  probed and returned HTTP 404, so another official CWA daily report, warning-history, archive, or
  weather-map source is still needed before assigning labels.
- Pending validation work: run live QPE/gauge reports for each selected event after matching
  event-time QPE grids are captured or an official historical QPE archive is confirmed.
- Pending training work: collect enough event windows for meaningful Tiny U-Net or NowcastNet
  training and reporting.

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
- Track QPE/gauge availability separately from completed validation reports when an official
  product is unavailable for historical timestamps.
- Attach official CWA weather context to every selected radar event before final weather labels are
  used for splitting or scientific reporting.
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
- Use threshold-weighted or focal-style losses plus validation early stopping before increasing
  model complexity.
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
