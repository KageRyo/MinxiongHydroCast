# Task List

This list replaces GitHub issues for now. Keep tasks small enough to finish, test, and propose
through a focused pull request. The end-to-end target is defined in
[completion_plan.md](completion_plan.md).

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
- [x] Add `mhc dataset-build` to orchestrate history discovery, resilient downloads, validation,
      tensor conversion, Persistence evaluation, catalog generation, and checksum verification.
- [x] Move formal research artifacts to a configurable durable root outside Git.
- [x] Replace formal demo split entries with two real train, one independent validation, and two
      held-out Minxiong/Chiayi test events.
- [x] Validate persisted dataset, training, and evaluation JSON through strict Pydantic schemas.
- [x] Train weighted Tiny U-Net with train-only normalization and a separate validation event.
- [x] Verify 251 cataloged external artifacts and retain the failed forecast-promotion blockers.
- [x] Add `mhc event-discover` with an incremental history cursor and both Minxiong-local and
      Taiwan-wide `35 dBZ` coverage metrics.
- [x] Preserve candidate radar windows with retry, resume, SHA-256, atomic writes, and bounded
      temporary scan-cache retention under the external research root.
- [x] Capture synchronized `O-B0045-001` QPE, `O-A0002-001` gauges, and WRA rainfall warnings in a
      strict Pydantic `EventEvidenceCatalog`.
- [x] Schedule candidate discovery every 20 minutes while preventing automatic formal-split edits.
- [x] Add auditable `mhc event-review` decisions and make `event-split-check` plus `dataset-build`
      reject incomplete, unapproved, checksum-invalid, time-mismatched, or regime-mismatched
      candidate promotions.
- [x] Preserve official review context as Pydantic-validated, atomically written, checksummed
      external artifacts while retaining URL-only catalog read compatibility.
- [x] Bound continuous candidates to cadence-aligned windows and start a new candidate instead of
      extending a sustained Taiwan-wide trigger without limit.
- [x] Complete the first checksummed official-context-backed `approved/convective` candidate review
      while keeping formal split membership `not_added`.
- [x] Review and reject two complete Taiwan-wide-only candidates with no Minxiong-local trigger,
      while preserving their evidence and leaving formal split membership `not_added`.
- [x] Keep Taiwan-wide threshold frames as persisted context metrics while limiting new candidate
      creation and extension to `minxiong_35dbz` triggers.
- [x] Deploy the event-discovery timer from `main`, verify the installed revision, and validate the
      live external catalog with zero artifact checksum or size errors.

## Next

### Immediate Operational Queue (Verified 2026-07-23)

Complete these items in order unless candidate review and code work are being handled independently.
Each code change should remain a focused pull request with its own tests and rollout evidence.

- [x] **P0 - Deploy and verify the WRA reliability change.** PR #24 installed revision `d6b770a`
      after 287 tests and two passing CI runs. Three live contracts, a healthy collector snapshot,
      the Prometheus retry metric, a 1,505-snapshot verified backup, and the unchanged rolling
      shadow evidence all passed their rollout checks. Retry exhaustion remains `schema_drift`.
- [x] **P0 - Add a read-only event review queue.** `mhc event-review-queue` verifies artifacts and
      ranks candidates using local radar, QPE, Minxiong gauges, warnings, official context, and
      evidence readiness. It does not edit the evidence catalog or formal split.
- [ ] **P0 - Close the pre-policy context-only review item.** Review and reject
      `cwa_o_a0059_candidate_20260715t0520`, which completed 35 of 35 frames with 22 Taiwan-wide
      triggers, zero Minxiong-local triggers, and formal membership `not_added`. Preserve all
      checksummed evidence and record the named reviewer.
- [ ] **P0 - Review the 11 complete Minxiong-local pending candidates.** The strict catalog now
      contains 15 complete candidates: one approved, two rejected, and 12 pending including the
      context-only item above. Start with the queue's 2026-07-17, 2026-07-16, and 2026-07-23
      candidates, then work through the remaining local candidates. Record an auditable approval
      or rejection and weather regime for each without changing the formal split. Do not classify
      a radar threshold crossing as heavy rain without official and gauge support.
- [ ] **P1 - Record shadow heavy-rain evidence only when review supports it.** If a reviewed local
      candidate establishes a bounded heavy-rain period, add its event ID, start/end times,
      official source, reviewer, and confirmation to the private deployed shadow-evidence file.
      Otherwise leave the count at zero and continue observation.
- [ ] **P1 - Recover and re-evaluate the rolling shadow gate.** Keep the scheduled collector and
      hourly evaluation running until there are at least 168 hours, 900 attempts, 99% success, 95%
      readiness, no ready gap over 30 minutes in the 192-hour window, intact storage, and one
      reviewed heavy-rain period. With no new gaps, the latest recorded over-30-minute gap remains
      in the window until approximately 2026-07-25 23:21 Asia/Taipei.
- [ ] **P1 - Publish candidate-review follow-up evidence.** After the pending reviews, update the
      dated deployment status, task checkboxes, catalog counts, reviewed regimes, and any
      evidence-backed shadow heavy-rain record.
- [ ] **P2 - Close external-use safeguards.** Replicate verified backups off-host, assign primary
      and backup human receivers, and exercise incident acknowledgement, override, rollback, and
      recovery before considering external operational use or notification delivery.

### Phase 1: Data Source Finalization

- [x] Confirm local WRA API key storage without committing the key.
- [x] Add a production CWA `O-A0002-001` rain-gauge adapter with strict Pydantic contracts,
      retry/backoff/rate limiting, source provenance, and scheduled live contract smoke testing.
- [x] Add the official WRA OpenApiv3 rainfall-warning adapter using the `apikey` header, strict
      Pydantic validation, request reliability controls, and source provenance.
- [x] Treat a valid WRA warning `Data=[]` response as healthy `outcome=empty` instead of an error.
- [x] Add the official WRA IoW flood-sensor adapter by joining government Open Data 142980 latest
      measurements with 142979 metadata and applying a 90-minute freshness limit.
- [x] Restrict scraper fallback to request failures and fail closed on schema drift, invalid units,
      broken joins, and unexpected empty observation sets.
- [x] Confirm WRA dataset 25768 is river/regional-drainage water level, not a valid substitute for
      street/community `flood_sensors`.
- [ ] Define a separate `river_water_levels` product and use case before integrating dataset 25768;
      preserve `checkresult`, `checkdesc`, observation time, and freshness.

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
- [x] Produce a checksummed dataset catalog and verification report under the external research
      root, with source provenance, time ranges, and lead-time metrics.
- [x] Add a next-batch event expansion queue from the existing CWA hourly discovery scan.
- [x] Let the first continuously collected candidate finish its post-trigger window, inspect
      official context and synchronized evidence, and record its `mhc event-review` decision
      without automatically changing a formal split.
- [ ] Human-review and accumulate typhoon, frontal, Mei-yu, and convective candidates before SOTA
      model migration.
- [ ] After sufficient reviewed diversity exists, propose a tracked formal-split change, rebuild
      the dataset, retrain, and rerun the unchanged Persistence promotion gate.

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
- [x] Compare the weighted Tiny U-Net with Persistence on one independent validation event and two
      held-out Minxiong/Chiayi test events.
- [ ] Improve the learned model until it consistently beats Persistence on aggregate and
      lead-time RMSE and CSI without weakening the promotion gate.
- [ ] Wire NowcastNet inference only after event diversity, code, checkpoint, tensor shape, and
      license are reviewed.

### Phase 5: Local Flood-Risk Layer

- [ ] Align radar/QPE, gauges, flood sensors, shelters, and risk areas to shared spatial
      references.
- [x] Publish snapshot-aligned references for gauges, sensors, shelters, pumping stations, and
      risk areas supplied to the operational collector.
- [ ] Align radar/QPE grids to the same operational location and township contract.
- [ ] Add Minxiong/Chiayi feature tables for rainfall, QPE accumulation, sensor status, and
      township/village context.
- [x] Add an operational Minxiong township feature row for rainfall, sensors, alerts, and stable
      location IDs.
- [x] Block readiness when official county feeds have no Minxiong rain-gauge or enabled
      flood-sensor coverage.
- [ ] Add validated QPE accumulation and village-level context to the operational feature table.
- [x] Define and audit provenance-backed Minxiong positive/negative flood labels.
- [ ] Collect enough confirmed labels to pass the 10-positive/20-negative training gate.
- [ ] Evaluate `RainfallThresholdRiskScorer` on real event windows.
- [ ] Add LightGBM/XGBoost only after labels and feature tables are stable.

### Phase 6: Operations

- [x] Publish the Minxiong/Chiayi baseline smoke-test model card.
- [ ] Publish model cards for any future Taiwan-wide or promoted Minxiong/Chiayi checkpoints.
- [x] Add locked one-shot and interval scheduling for rainfall-alert and hydrology ingestion.
- [x] Add immutable checksummed snapshots, latest pointers, retention, and failed-attempt records.
- [x] Add freshness/schema/readiness health checks and a versioned read API.
- [x] Add a localhost operator view separating official-source data and experimental forecasts.
- [x] Add systemd collector timer and API supervision templates for Linux deployment.
- [x] Add a shadow-history report with heavy-rain evidence and an explicit notification blocker.
- [x] Add a scheduled official-source live contract workflow that requires `CWA_API_KEY` and
      `WRA_API_KEY` repository secrets without printing credentials.
- [x] Deploy the localhost single-host profile on durable storage and enable persistent user
      services, monitoring, local alert auditing, backup, and shadow timers.
- [x] Deploy the supplied user-systemd units on the managed host with least-privilege secret
      delivery, localhost-only access, and documented rollback instructions.
- [ ] Add authenticated TLS ingress only before making the service reachable beyond localhost.
- [x] Put snapshots on durable mounted storage, schedule local backups, and verify a restore.
- [x] Scrape service metrics and route failed/stale/degraded/schema alerts to the durable local audit
      receiver.
- [ ] Route operational alerts to named primary and backup human receivers.
- [ ] Complete the seven-day shadow gate with 900 attempts, 99% collection success, 95% readiness,
      no gap over 30 minutes, intact snapshots, and a reviewed heavy-rain period.
- [ ] Exercise incident response, operator override, and recovery before enabling notifications.
- [x] Keep deployment configuration separate from research/training artifacts.

## Later

- [x] Schedule stable observation collection, shadow evaluation, backups, and official live
      contracts.
- [ ] Replicate verified backups to a different device or remote system before external operational
      use; the current local backup does not cover loss of the host or storage volume.
- [ ] Schedule radar/model workflows only after their data and model gates are stable.
- [ ] Extend the operator view with experimental forecast products only after model outputs pass
      their gates.
