# Roadmap

This roadmap turns FloodCastTW into a usable flood-risk data and nowcasting platform. Keep each
milestone small enough to become GitHub issues.

## Milestone 1: Stabilize Live Data Ingestion

- [ ] Implement live WRA rain gauge parsing in `src/floodcasttw/ingestion/hydrological_data.py`.
- [ ] Implement live WRA flood-sensor parsing with explicit station, time, water level, and status fields.
- [ ] Add source metadata to every live capture: URL, fetch time, mode, row count, and failure reason.
- [ ] Save raw captures or screenshots locally under ignored `data/raw/` for parser debugging.
- [ ] Keep `demo` and `live` modes separate in every ingestion command.

## Milestone 2: Validate and Normalize Data

- [ ] Define schema checks for rainfall alerts, rain gauges, flood sensors, shelters, and pumping stations.
- [ ] Reject production runs containing `資料模式=demo`.
- [ ] Normalize timestamps to ISO 8601 with timezone.
- [ ] Convert rainfall and water-level fields to numeric values plus units.
- [ ] Add tests for parser edge cases and validation failures.

## Milestone 3: Build Spatial Alignment

- [ ] Standardize coordinates to WGS84 and keep original coordinate columns when available.
- [ ] Add station and sensor location tables with stable IDs.
- [ ] Align gauges, flood sensors, pumping stations, shelters, and flood-risk areas to township/village units.
- [ ] Design a grid format for radar rainfall and model outputs.
- [ ] Document assumptions for Minxiong, Chiayi County, and Taiwan-wide scaling.

## Milestone 4: Establish Baseline Models

- [ ] Evaluate `PersistenceNowcaster` on gridded rainfall or radar-like tensors.
- [ ] Evaluate `RainfallThresholdRiskScorer` against historical warnings or flood events.
- [ ] Add metrics: RMSE for rainfall, and CSI/POD/FAR for event prediction.
- [ ] Create a repeatable evaluation script under `src/floodcasttw/models/` or `pipelines/`.
- [ ] Publish baseline results before adding deep-learning models.

## Milestone 5: Prepare SOTA Migration

- [ ] Confirm radar data format, cadence, projection, and licensing.
- [ ] Decide where external checkpoints and datasets live outside git.
- [ ] Map Taiwan radar tensors into the `NowcastNetAdapter` input contract.
- [ ] Run a small inference-only smoke test before training.
- [ ] Compare NowcastNet-style output against the persistence baseline.

## Milestone 6: Operationalize

- [ ] Add scheduled jobs only after ingestion and validation are stable.
- [ ] Emit structured logs and run summaries for every pipeline execution.
- [ ] Add CI for tests and linting.
- [ ] Add GitHub issues for each unchecked roadmap item.
