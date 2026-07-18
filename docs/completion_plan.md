# Completion Plan

MinxiongHydroCast has separate completion levels. The internal observation service may be usable
before an experimental nowcast is scientifically credible, and neither state makes the project an
official warning system. A full forecast product is production-ready only when it can continuously
ingest and validate official data, produce versioned Minxiong risk inputs and nowcasts, expose them
through a monitored service, and publish a documented Minxiong model without committing
credentials, raw official data, or model weights.

## Completion Levels

1. **Internal observation service:** official-source collection, immutable snapshots, readiness,
   localhost API/operator view, monitoring, local alert audit, backup/restore, and supervised
   scheduling are implemented and deployed. External operational use still requires the real
   shadow gate, off-host recovery, named operators, and exercised incident paths.
2. **Experimental rainfall nowcast:** reproducible independent-event evaluation is implemented;
   event diversity, QPE/gauge validation, local labels, calibration, and passing model-promotion
   evidence remain incomplete.
3. **Public operational service:** authenticated/TLS ingress, approved SLOs and data rights, named
   decision authority, human override, and communication gates are required before any external
   operational use.

## Forecast Product Definition Of Done

- CWA radar/QPE research ingestion and CWA/WRA operational ingestion run from documented local
  configuration.
- Multi-frame CWA radar events can be collected, inspected, converted, and evaluated.
- Event-based train/validation/test splits are populated with real historical weather events.
- A persistence baseline, a small trainable neural baseline, and a SOTA migration candidate are
  evaluated with the same metrics.
- A Minxiong/Chiayi model card documents data sources, limitations, metrics, and attribution.
- CI covers unit tests, linting, dry-run contract checks, and production configuration validation.
- A scheduler retries ingestion idempotently and raises alerts for stale, missing, or invalid data.
- Versioned outputs are stored durably and served through a localhost-only operator surface or an
  authenticated network API.
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
- Completed: historical three-event QPE/gauge availability status manifest. CWA `O-A0002-001`
  gauge captures parse, but event-time `O-B0045-001` QPE history probes return HTTP 404. This is
  supporting source evidence rather than the active five-event split.
- Completed: event weather-context manifest that prevents radar-only windows from being mislabeled
  before official CWA evidence is attached.
- Completed: CWA official weather-context source review manifest listing reviewed CWA pages,
  current coverage, and next historical chart probe URLs.
- Completed: `mhc dataset-build` orchestration for CWA history, resilient event download, sequence
  validation, tensor conversion, Persistence evaluation, weighted Tiny U-Net evaluation, catalog
  generation, and checksum verification in an external durable research root.
- Completed: deployed `mhc event-discover` on a 20-minute user-systemd timer with incremental
  `O-A0059-001` scanning, local/Taiwan `35 dBZ` metrics, resumable checksummed event windows, and
  synchronized QPE/gauge/warning evidence. The Pydantic catalog and `mhc event-review` gate keep
  discovery candidates out of formal splits until an auditable human decision.
- Completed: checksummed official-context artifacts for `mhc event-review`, including publisher,
  source URL, published/fetched times, atomic external preservation, catalog verification, and
  backward-compatible reading of URL-only reviews.
- Completed: cadence-aligned maximum candidate windows that split sustained trigger sequences while
  preserving existing candidate identifiers, evidence, and older catalog compatibility.
- Completed: Minxiong-local candidate eligibility. Taiwan-wide threshold labels remain persisted
  frame context, but cannot create or extend the human-review queue without `minxiong_35dbz`.
- Completed: formal five-event split with two real train, one independent validation, and two
  held-out Minxiong/Chiayi test events; all formal demo placeholders are prohibited by schema.
- Completed: weighted Tiny U-Net run on two RTX 4090 GPUs using 88 training windows and a separate
  26-window validation event. It improves aggregate RMSE but fails the independent promotion gate
  on CSI and lead-time regressions, so forecast publication remains disabled.
- Completed: Pydantic contracts for dataset manifests, CWA history and collection artifacts,
  training/evaluation results, catalog records, and checksum verification reports.
- Completed: verified 251 external artifacts totaling 2,410,640,934 bytes with no checksum or size
  mismatches.
- Completed: baseline model card for Minxiong/Chiayi-oriented smoke testing.
- Completed: local WRA API key configuration; real key stays in ignored `.env`.
- Completed: locked one-shot/interval observation collection, immutable checksummed snapshots,
  retention, last-attempt tracking, dynamic freshness/schema readiness, a versioned read API, and
  a localhost operator view.
- Completed: official CWA `O-A0002-001` operational rain-gauge adapter with strict Pydantic input
  schemas, retry/backoff/rate limiting, WGS84/station identifiers, source provenance, degraded
  scraper fallback, and a scheduled credential-safe live contract smoke test.
- Completed: official WRA OpenApiv3 rainfall-warning adapter and WRA IoW flood-depth Open Data
  adapter, including strict Pydantic contracts, healthy empty-warning semantics, paginated
  measurement/metadata joins, provenance, and request-only degraded fallback.
- Completed: the canonical single-host runtime with user-systemd supervision, Prometheus scraping,
  Alertmanager routing to a durable local audit receiver, scheduled local backup/restore, hourly
  shadow evaluation, and an online host-bound GitHub Actions runner. See
  [deployment_status.md](deployment_status.md) for dated evidence.
- Completed: deployed bounded backup lock retry. A live collector/backup collision waited and
  recovered, then the resulting archive passed checksum verification.
- Active operational evidence: at 2026-07-18 14:29 the current snapshot was healthy, all supervised
  services and timers were operating, and the latest verified daily backup contained 748
  snapshots. The rolling shadow window contained 819 attempts over 134.760 hours, with 98.0464%
  success, 96.7033% readiness, a 50.017-minute maximum gap, intact storage, and no confirmed
  heavy-rain period.
- Active candidate evidence: the strict catalog contained nine candidates and zero artifact
  errors. Five complete candidates awaited review, including four created by Minxiong-local
  triggers; one additional local candidate was still collecting. All remain outside the formal
  split.
- Deferred for the current internal localhost stage: replicate backups to another device or remote
  system. The accepted risk must be resolved before external operational use.
- Pending operational safeguards: assign primary and backup operators, route alerts to a named human
  receiver, exercise incident/override/rollback procedures, and complete the real shadow gate.
- Pending reliability work: add bounded retries for demonstrably transient invalid WRA payloads or
  inconsistent pagination while retaining strict Pydantic fail-closed behavior for persistent
  schema changes. The current rolling window contains 16 WRA-related failed attempts.
- Pending public exposure work: define SLOs and add authenticated TLS ingress only if the service
  must become reachable beyond localhost.
- Pending optional hydrology work: define a separate operational use case and contract before
  integrating river/regional-drainage water levels; never substitute them for flood-depth sensors.
- Pending official-label work: attach CWA weather maps, warnings, daily reports, or equivalent
  official source evidence to each selected event before weather-type stratification.
- Pending source-search work: candidate event-time CWA historical `SFCcombo` chart URLs were
  probed and returned HTTP 404, so another official CWA daily report, warning-history, archive, or
  weather-map source is still needed before assigning labels.
- Pending validation work: run live QPE/gauge reports for each selected event after matching
  event-time QPE grids are captured or an official historical QPE archive is confirmed.
- Completed evidence work: the first continuously collected candidate reached 116 of 116 frames,
  passed full artifact verification, received a checksummed official-context-backed
  `approved/convective` review, and remained outside the formal split. Repeating the same review was
  idempotent. Two subsequent complete Taiwan-wide-only candidates were reviewed as
  `rejected/unclassified`; catalog verification remained clean and the formal split checksum did
  not change.
- Next technical focus: harden transient WRA response handling, close the preserved context-only
  review item, and review the complete Minxiong-local candidates collected from July 15 through
  July 18. Record a shadow heavy-rain period only when the reviewed radar, gauge, QPE, warning, and
  official context evidence supports it. Only after the dataset becomes meaningfully more diverse
  should the formal split change, the model retrain, and the unchanged independent-event gate
  rerun. Do not consider NowcastNet or forecast publication before those evidence gaps close.

## Phase 1: Data Source Finalization

- Live-verify CWA historyAPI endpoint and retention for `O-A0059-001`.
- Download a short multi-frame radar sequence under `data/external/radar/`.
- Extend event planning from file-list selection to actual frame download.
- Add schema checks for every frame in a sequence: timestamp spacing, grid consistency, units, and
  nodata encoding.
- Live-verify and continuously monitor the WRA rainfall-warning and IoW flood-depth contracts.

## Phase 2: Dataset Build

- Maintain `mhc dataset-build` as the canonical checksummed external-dataset workflow.
- Expand `data/samples/event_split_manifest.json` with weather-diverse real historical events.
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

## Phase 6: Operations

- Publish model cards for Taiwan-wide and Minxiong/Chiayi-specific checkpoints.
- Add scheduled jobs only after manual ingestion and validation are repeatable.
- Add alerting only after run summaries expose reliable failure reasons.
- Keep deployment configuration separate from research/training artifacts.
