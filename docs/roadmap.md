# Roadmap

This roadmap turns FloodCastMinxiong into a usable flood-risk data and nowcasting platform. Keep each
milestone small enough to track in [tasks.md](tasks.md). The completion definition and phase-by-phase
exit criteria are maintained in [completion_plan.md](completion_plan.md).

## Milestone 1: Stabilize Live Data Ingestion

- [x] Implement live WRA rain gauge parsing in `src/floodcastminxiong/ingestion/hydrological_data.py`.
- [x] Implement live WRA flood-sensor parsing with explicit station, time, water level, and status fields.
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
- [x] Create a repeatable evaluation script under `src/floodcastminxiong/models/` or `pipelines/`.
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
- [x] Track per-event QPE/gauge validation availability without committing raw official data.
- [ ] Add gauge/QPE validation reports for each dataset build after event-time QPE grids are
      captured or an official historical QPE archive is confirmed.

## Milestone 7: Train And Compare Models

- [x] Convert CWA event sequences into tensor archives with CRS, timestamp, and nodata metadata.
- [x] Evaluate persistence on real converted event tensors.
- [x] Add a small U-Net baseline training entrypoint for one RTX 4090.
- [x] Add checkpoint save/resume and deterministic training summaries.
- [x] Run the Tiny U-Net smoke baseline on two RTX 4090 GPUs.
- [x] Add nodata masking and radar tensor normalization for neural smoke training.
- [x] Compare persistence and Tiny U-Net smoke outputs with the same metrics and mask.
- [ ] Collect longer event datasets for meaningful neural training.
- [ ] Migrate NowcastNet only after license and tensor compatibility are reviewed.

## Milestone 8: Operationalize

- [ ] Replace page scraping with approved WRA API contracts for production-critical feeds.
- [x] Package rainfall-alert and hydrology ingestion as a locked, repeatable scheduled job.
- [x] Store immutable, checksummed observation snapshots with latest and last-attempt pointers.
- [x] Expose freshness, schema drift, failed-run, and missing-forecast health states.
- [ ] Add feature assembly and forecast publication to the scheduled operational flow.
- [ ] Add a remote durable-storage backend and deployment backups.
- [ ] Export metrics and route failed/stale/schema alerts to named maintainers.
- [x] Emit structured logs and run summaries for every pipeline execution.
- [x] Add CI for tests and linting.
- [x] Maintain a repo task list for unchecked roadmap items.
- [x] Publish a Minxiong/Chiayi baseline model card before distributing checkpoints.

## Milestone 9: Deliver A Minxiong Service

- [ ] Define users, decisions, update cadence, latency, and data-freshness SLOs with local operators.
- [x] Publish a versioned read API for current alerts and observations.
- [x] Add an operator view that separates official-source data from experimental predictions.
- [x] Add systemd templates for a persistent collector timer and supervised localhost API.
- [x] Add an auditable seven-day shadow gate requiring reviewed heavy-rain coverage.
- [x] Add a provenance-backed Minxiong flood-label audit and minimum class-coverage gate.
- [ ] Publish forecast grids and risk features after their model/data gates pass.
- [ ] Backtest on multiple independent events and calibrate thresholds with local flood labels.
- [ ] Run a shadow deployment through at least one heavy-rain period before enabling notifications.
- [ ] Document incident response, data licensing, model rollback, and human override procedures.
