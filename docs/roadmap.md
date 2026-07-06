# Roadmap

This roadmap turns FloodCastTW into a usable flood-risk data and nowcasting platform. Keep each
milestone small enough to track in [tasks.md](tasks.md).

## Milestone 1: Stabilize Live Data Ingestion

- [x] Implement live WRA rain gauge parsing in `src/floodcasttw/ingestion/hydrological_data.py`.
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
- [x] Create a repeatable evaluation script under `src/floodcasttw/models/` or `pipelines/`.
- [x] Publish baseline results before adding deep-learning models.

## Milestone 5: Prepare SOTA Migration

- [x] Identify official CWA radar/QPE candidate data IDs, cadence, formats, and license URL.
- [x] Add a CWA file API downloader with dry-run support and key redaction.
- [x] Confirm CWA radar/QPE projection, grid origin, shape, timestamps, and nodata encoding from
      downloaded sample files.
- [ ] Confirm CWA historyAPI retention and collect multi-frame event sequences.
- [x] Decide where external checkpoints and datasets live outside git.
- [x] Define the provisional Taiwan radar tensor contract for `NowcastNetAdapter`.
- [x] Run a small inference-only smoke test before training.
- [x] Compare the adapter tensor contract against the persistence baseline.

## Milestone 6: Operationalize

- [ ] Add scheduled jobs only after ingestion and validation are stable.
- [x] Emit structured logs and run summaries for every pipeline execution.
- [x] Add CI for tests and linting.
- [x] Maintain a repo task list for unchecked roadmap items.
