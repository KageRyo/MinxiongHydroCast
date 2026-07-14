# Roadmap

This roadmap turns MinxiongHydroCast into a usable flood-risk data and nowcasting platform. Keep each
milestone small enough to track in [tasks.md](tasks.md). The completion definition and phase-by-phase
exit criteria are maintained in [completion_plan.md](completion_plan.md).

## Milestone 1: Stabilize Live Data Ingestion

- [x] Retain WRA rain-gauge and flood-sensor page parsers for degraded fallback diagnostics.
- [x] Implement official-source adapters with explicit station, time, value, unit, and status fields.
- [x] Add source metadata to every live capture: URL, fetch time, mode, row count, and failure reason.
- [x] Save raw captures or screenshots locally under ignored `data/raw/` for parser debugging.
- [x] Keep `demo` and `live` modes separate in every ingestion command.

## Milestone 2: Validate and Normalize Data

- [x] Define schema checks for rainfall alerts, rain gauges, flood sensors, shelters, and pumping stations.
- [x] Reject production runs containing `資料模式=demo`.
- [x] Normalize timestamps to ISO 8601 with timezone.
- [x] Convert rainfall and water-level fields to numeric values plus units.
- [x] Add tests for parser edge cases and validation failures.

## Milestone 3: Build Spatial Alignment

- [x] Standardize coordinates to WGS84 and keep original coordinate columns when available.
- [x] Add station and sensor location tables with stable IDs.
- [x] Align gauges, flood sensors, pumping stations, shelters, and flood-risk areas to township/village units.
- [x] Design a grid format for radar rainfall and model outputs.
- [x] Document assumptions for Minxiong, Chiayi County, and Taiwan-wide scaling.

## Milestone 4: Establish Baseline Models

- [x] Evaluate `PersistenceNowcaster` on gridded rainfall or radar-like tensors.
- [x] Evaluate `RainfallThresholdRiskScorer` against historical warnings or flood events.
- [x] Add metrics: RMSE for rainfall, and CSI/POD/FAR for event prediction.
- [x] Create a repeatable evaluation script under `src/minxionghydrocast/models/` or `pipelines/`.
- [x] Publish baseline results before adding deep-learning models.

## Milestone 5: Prepare SOTA Migration

- [x] Identify official CWA radar/QPE candidate data IDs, cadence, formats, and license URL.
- [x] Add a CWA file API downloader with dry-run support and key redaction.
- [x] Confirm CWA radar/QPE projection, grid origin, shape, timestamps, and nodata encoding from
      downloaded sample files.
- [x] Add a dry-run CWA history file-list client and event planning skeleton.
- [x] Live-verify CWA historyAPI retention and collect multi-frame event sequences.
- [x] Decide where external checkpoints and datasets live outside git.
- [x] Define the provisional Taiwan radar tensor contract for `NowcastNetAdapter`.
- [x] Run a small inference-only smoke test before training.
- [x] Compare the adapter tensor contract against the persistence baseline.

## Milestone 6: Build Historical Radar Dataset

- [x] Collect short multi-frame CWA radar sequences under ignored `data/external/`.
- [x] Build event plans for Chiayi/Minxiong heavy-rain windows and Taiwan-wide radar-derived
      candidate events.
- [x] Populate tracked event split manifests with real historical event metadata.
- [x] Produce reproducible dataset summaries without committing official raw data.
- [x] Add a durable external research root and a single `mhc dataset-build` orchestration command.
- [x] Build a formal 2-train/1-validation/2-local-test dataset with no demo placeholders.
- [x] Catalog and verify every dataset artifact with provenance, time ranges, SHA-256, and
      lead-time metrics.
- [x] Track per-event QPE/gauge validation availability without committing raw official data.
- [ ] Add gauge/QPE validation reports for each dataset build after event-time QPE grids are
      captured or an official historical QPE archive is confirmed.
- [x] Add continuous 20-minute `O-A0059-001` event discovery with local and Taiwan-wide `35 dBZ`
      coverage, resumable candidate windows, and synchronized QPE/gauge/warning evidence.
- [x] Enforce a Pydantic candidate queue that requires human review and cannot update formal splits.
- [x] Record reviewer, review time, regime, and official context through `mhc event-review`, and
      reject unapproved promotion in both `event-split-check` and `dataset-build`.
- [x] Catalog exact official-context files with publisher and publication/fetch times, byte size,
      SHA-256, atomic external storage, and tamper verification.
- [x] Deploy continuous discovery on the managed host and verify its installed revision, 20-minute
      timer, incremental live run, and external catalog checksums.
- [ ] Complete an official-context-backed human review of the first finished continuous candidate
      while keeping formal split selection as a separate tracked decision.
- [ ] Accumulate reviewed typhoon, frontal, Mei-yu, and convective candidates before retraining.

## Milestone 7: Train And Compare Models

- [x] Convert CWA event sequences into tensor archives with CRS, timestamp, and nodata metadata.
- [x] Evaluate persistence on real converted event tensors.
- [x] Add a small U-Net baseline training entrypoint for one RTX 4090.
- [x] Add checkpoint save/resume and deterministic training summaries.
- [x] Run the Tiny U-Net smoke baseline on two RTX 4090 GPUs.
- [x] Add nodata masking and radar tensor normalization for neural smoke training.
- [x] Compare persistence and Tiny U-Net smoke outputs with the same metrics and mask.
- [x] Train with train-only normalization and an independent event validation archive.
- [x] Evaluate weighted Tiny U-Net against Persistence on two held-out Minxiong/Chiayi events and
      fail closed when the promotion gate does not pass.
- [ ] Promote newly reviewed, weather-diverse candidates into formal splits, then retrain and rerun
      the unchanged Persistence gate.
- [ ] Migrate NowcastNet only after license and tensor compatibility are reviewed.

## Milestone 8: Operationalize

- [x] Make official machine-readable sources primary for all three operational observation feeds;
      retain page scraping only as an explicit degraded request-failure fallback.
- [x] Replace operational rain-gauge scraping with the official CWA `O-A0002-001` API adapter,
      strict upstream schemas, reliable requests, provenance, and degraded fallback semantics.
- [x] Add the WRA OpenApiv3 rainfall-warning adapter with `apikey` header authentication, strict
      Pydantic validation, and a healthy `outcome=empty` for valid `Data=[]` responses.
- [x] Join WRA IoW government Open Data 142980 measurements with 142979 sensor metadata and enforce
      a 90-minute freshness limit for the approximately hourly public snapshot.
- [x] Fail closed on official-source schema drift and permit scraper fallback only for request
      failures.
- [x] Review WRA river/regional-drainage water-level dataset 25768 and prohibit substituting it for
      `flood_sensors`.
- [ ] Add a separate `river_water_levels` contract only after an operational use case is defined;
      retain upstream quality flags and do not feed it into current Minxiong flood features.
- [x] Package rainfall-alert and hydrology ingestion as a locked, repeatable scheduled job.
- [x] Store immutable, checksummed observation snapshots with latest and last-attempt pointers.
- [x] Expose freshness, schema drift, failed-run, and missing-forecast health states.
- [ ] Add forecast publication to the scheduled operational flow after model gates pass.
- [x] Add snapshot-native Minxiong observation/alert features with stable location IDs.
- [ ] Add validated QPE and experimental forecast fields to the feature contract.
- [x] Add scheduled checksummed local backups and verify isolated restore.
- [ ] Replicate verified backups to a different device or remote system before external operational
      use; the current local backup does not cover loss of the host or storage volume.
- [x] Export readiness, age, state, and shadow-gate metrics.
- [x] Scrape metrics with Prometheus and route failed/stale/degraded/schema alerts to the durable
      local audit receiver.
- [ ] Route operational alerts to named primary and backup maintainers.
- [x] Emit structured logs and run summaries for every pipeline execution.
- [x] Add CI for tests and linting.
- [x] Maintain a repo task list for unchecked roadmap items.
- [x] Publish a Minxiong/Chiayi baseline model card before distributing checkpoints.

## Milestone 9: Deliver A Minxiong Service

- [ ] Define users, decisions, update cadence, latency, and data-freshness SLOs with local operators.
- [x] Publish a versioned read API for current alerts and observations.
- [x] Add an operator view that separates official-source data from experimental predictions.
- [x] Add systemd templates for a persistent collector timer and supervised localhost API.
- [x] Deploy the localhost single-host profile with persistent services and least-privilege secret
      delivery on durable storage.
- [x] Deploy the supplied units on the managed host with least-privilege secrets, localhost-only
      access, and documented rollback.
- [ ] Add authenticated TLS ingress only before making the service network-accessible.
- [x] Add an auditable seven-day shadow gate requiring reviewed heavy-rain coverage.
- [x] Add a provenance-backed Minxiong flood-label audit and minimum class-coverage gate.
- [ ] Publish forecast grids and risk features after their model/data gates pass.
- [x] Publish the observation-derived Minxiong feature contract.
- [x] Require explicit Minxiong rain-gauge and enabled flood-sensor coverage before feature
      readiness can pass.
- [ ] Backtest on multiple independent events and calibrate thresholds with local flood labels.
- [ ] Complete the seven-day shadow deployment before enabling notifications: 900 attempts, 99%
      collection success, 95% readiness, no gap over 30 minutes, intact snapshots, and reviewed
      heavy-rain coverage.
- [x] Put operational snapshots on durable storage and verify scheduled backup restore.
- [ ] Route operational alerts to named owners and exercise incident response and human override.
- [x] Document incident response, data-source rights review, model rollback, and human override
      procedures.
