# MinxiongHydroCast

[![CI](https://github.com/KageRyo/MinxiongHydroCast/actions/workflows/ci.yml/badge.svg)](https://github.com/KageRyo/MinxiongHydroCast/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Style: Ruff](https://img.shields.io/badge/style-ruff-46a6ff)](https://docs.astral.sh/ruff/)
[![Service](https://img.shields.io/badge/service-observation%20service-blue)](docs/operational_use.md)
[![Operational Gate](https://img.shields.io/badge/operational%20gate-pending-orange)](docs/operational_use.md#production-gates)

Minxiong-first hydrometeorological observation and rainfall-nowcasting toolkit.

MinxiongHydroCast is a Minxiong-first hydrometeorological observation and rainfall-nowcasting
toolkit. Its operational target is Minxiong Township, while Taiwan-wide radar data is used as
upstream training and context data. The repository includes a live official-source observation
service and is no longer demo-only. It is still an internal research and data-engineering system,
not an official warning system or a production-ready public service.

## What This Repo Does

- Collect active WRA rainfall warnings for Chiayi County from the official OpenApiv3 endpoint.
- Ingest live CWA rain-gauge observations and WRA IoW flood-depth snapshots with strict schemas.
- Keep explicit demo fixtures for installation checks and deterministic tests.
- Parse shelter DOCX files into structured CSV without committing source documents.
- Keep raw, interim, processed, and sample data separate.
- Build stable location references for gauges, sensors, shelters, pumping stations, and risk areas.
- Provide baseline models before deep-learning training is justified.
- Prepare a `NowcastNetAdapter` boundary for future SOTA migration.
- Track official CWA radar/QPE candidate sources without committing raw downloads or API keys.

## What You Can Use Today

Today the repository is useful for four concrete workflows:

- ingest and validate live WRA rainfall warnings, CWA rain gauges, and WRA IoW flood sensors;
- collect reproducible CWA radar event windows and convert them to model-ready tensors;
- benchmark persistence and Tiny U-Net nowcasting with common lead-time metrics;
- assemble Minxiong/Chiayi location references and flood-risk features for downstream systems.

It includes a local operational observation service, versioned snapshots, health/readiness checks,
a read-only API, and an operator view. It is not deployed as a public service and does not provide
a validated public flood warning. See [docs/operational_use.md](docs/operational_use.md) for
operating profiles, storage contracts, and the gates required before public deployment.

## Quick Start

```bash
conda env create -f environment.yml
conda activate minxiong-hydrocast
python -m playwright install chromium
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

`pyproject.toml` is the single source of truth for Python dependencies. Install `.[dev]` for
linting and tests, `.[model]` for model training, or `.[dev,model]` when both are needed.

Use the concise `mhc` dispatcher for interactive commands:

```bash
mhc --help
mhc operations --help
mhc serve --help
mhc dataset-build --help
```

Every existing `minxiong-hydrocast-<command>` entry point is available as `mhc <command>`.
`mhc collect` aliases `mhc operations`, and `mhc shadow` aliases `mhc shadow-report`. The full
entry points remain available for explicit service definitions and automation.

## Reproducible Radar Research

The formal CWA radar dataset is built in a durable root outside Git. Set
`MINXIONGHYDROCAST_RESEARCH_ROOT` in the ignored `.env`, load the environment, and run:

```bash
set -a
source .env
set +a

mhc dataset-build \
  --manifest data/samples/event_split_manifest.json \
  --root "$MINXIONGHYDROCAST_RESEARCH_ROOT" \
  --train-weighted-unet \
  --epochs 20 \
  --hidden-channels 8 \
  --batch-size 2 \
  --event-weight 4 \
  --early-stopping-patience 5 \
  --device cuda \
  --multi-gpu
```

The command orchestrates CWA history discovery, event download, sequence validation, tensor
conversion, Persistence evaluation, independent validation, weighted Tiny U-Net training and
testing, catalog generation, and SHA-256 verification. The current five-event build has two train,
one validation, and two held-out Minxiong/Chiayi test events. The learned model improves aggregate
RMSE but does not consistently beat Persistence on CSI and lead-time gates, so forecast
publication remains disabled. See [docs/research_dataset.md](docs/research_dataset.md).

## Operational Observation Service

Create a versioned demo snapshot without contacting live sources:

```bash
mhc operations --mode demo --once
```

Run one live collection. Live is the default mode. Store both keys in an ignored local `.env`
created from `env.example`, then export it into the process environment:

```bash
set -a
source .env
set +a

mhc operations --once \
  --alert-source auto \
  --rain-source auto \
  --flood-source auto \
  --flood-max-age-minutes 90
```

The primary sources are:

- WRA OpenApiv3 `GET /v2/Rainfall/Warning`, authenticated with `WRA_API_KEY` in the `apikey`
  request header, for active rainfall warnings;
- CWA `O-A0002-001`, authenticated with `CWA_API_KEY`, for rain gauges;
- WRA IoW government Open Data [142980](https://data.gov.tw/dataset/142980) joined with
  [142979](https://data.gov.tw/dataset/142979) for flood-depth sensors.

Each `--alert-source`, `--rain-source`, and `--flood-source` selector accepts `api`, `auto`, or
`scraper`. `auto` uses the official source and falls back to the corresponding WRA page only for
authentication, timeout, transport, HTTP, or rate-limit failures. The fallback is recorded as
`scraper_fallback`, published as `degraded`, and never satisfies readiness. Strict Pydantic schema
drift, invalid timestamps/units, broken IoW joins, and unexpected empty observation sets fail the
attempt without fallback. Use `api` to fail on any request error, and reserve `scraper` for a
documented source incident.

The WRA warning endpoint reports only active warnings. A validated `Data=[]` response is therefore
a healthy zero-row `outcome=empty`, not a collection error. The IoW feed is an official public
snapshot published approximately hourly, not the bearer-protected station-origin real-time feed;
the collector applies a separate 90-minute freshness limit.

Smoke-test all three official observation contracts without installing a Playwright browser:

```bash
mhc cwa-rain-smoke --county 10010 --county-name 嘉義縣
mhc wra-alert-smoke --county 10010
mhc wra-flood-smoke --county 10010
```

Run the collector every 10 minutes and retain 30 days of snapshots:

```bash
mhc operations \
  --interval-seconds 600 \
  --retention-days 30 \
  --max-age-minutes 30 \
  --flood-max-age-minutes 90 \
  --alert-source auto \
  --rain-source auto \
  --flood-source auto \
  --pumping-stations data/processed/pumping_stations.csv \
  --shelters data/processed/shelters.csv \
  --flood-risk-areas data/processed/flood_risk_areas.csv
```

Serve the read-only API and internal operator view on localhost:

```bash
mhc serve --host 127.0.0.1 --port 8080
```

Open <http://127.0.0.1:8080/> for the operator view. The service exposes:

- `GET /healthz` for process liveness;
- `GET /readyz` for data readiness, with HTTP 503 for demo, stale, invalid, or failed data;
- `GET /metrics` for Prometheus-compatible readiness, attempt, age, state, and source metrics;
- `GET /api/v1/status` for the latest attempt, snapshot, and dataset health;
- `GET /api/v1/official-alerts/rainfall`;
- `GET /api/v1/observations/rain-gauges`;
- `GET /api/v1/observations/flood-sensors`;
- `GET /api/v1/features/minxiong` for the derived township feature contract;
- `GET /api/v1/locations` for snapshot-aligned gauges, sensors, shelters, pumps, and risk areas;
- `GET /api/v1/shadow-readiness` for the audited shadow gate and notification blockers;
- `GET /api/v1/experimental-forecasts`, which remains unavailable until model and shadow gates
  pass.

Snapshots are immutable under `data/processed/operations/snapshots/`. A failed collection updates
`latest_attempt.json` but does not replace the last readable `latest.json` snapshot.
Each dataset manifest and API response includes source kind, authority, dataset ID, redacted URL,
fetch time, adapter schema version, content SHA-256, outcome, and any fallback reason.
For a Linux host, basic system service templates are provided under `deploy/systemd/`. The complete
single-host profile, including durable storage, monitoring, alert auditing, backup/restore,
optional Discord delivery, and shadow scheduling, is under `deploy/systemd-user/` and
`deploy/single-host/`; see
[docs/single_host_operations.md](docs/single_host_operations.md).

Evaluate accumulated live snapshots against a reviewed heavy-rain period:

```bash
mhc shadow-report \
  --evidence /path/to/reviewed_shadow_evidence.json
```

The default gate requires seven days, 900 live attempts, 99% collection success, 95% readiness,
no gap over 30 minutes, intact snapshots, and at least one continuously covered heavy-rain period.
Passing this gate does not enable notifications; local model-label and delivery gates remain.

Audit reviewed Minxiong flood-event labels before using them for model training:

```bash
mhc label-audit \
  --manifest /path/to/reviewed_flood_labels.json \
  --output data/processed/flood_label_audit.json \
  --require-training-ready
```

The tracked `data/samples/flood_labels.example.json` is an unconfirmed schema example and is
deliberately rejected. The default training gate requires at least 10 confirmed flood events and
20 confirmed non-flood events with non-overlapping windows and source/reviewer provenance.

Each successful operational snapshot also contains `minxiong_features.csv`. It aggregates only
validated Minxiong records and links gauges/sensors to stable location IDs. Readiness requires at
least one Minxiong rain gauge and one enabled Minxiong flood-depth sensor; `coverage_ready` and
`coverage_gaps` make missing target coverage explicit. QPE and experimental
forecast fields remain explicitly unavailable until their upstream products pass validation.
The same snapshot contains `location_reference.csv`; current gauges and sensors are always
included, while shelters, pumping stations, and risk areas are included only from explicitly
provided processed CSV inputs.

Run the local demo pipeline for installation and schema checks only:

```bash
mhc demo
```

The standalone rainfall-alert and hydrology CLIs below exercise the legacy page parsers. Keep them
for fixture generation and managed fallback diagnostics; use `minxiong-hydrocast-operations` for
the official-source operational path.

Run rainfall-alert parser diagnostics:

```bash
# Demo data
minxiong-hydrocast-rainfall-alerts --mode demo

# Direct WRA page parser for Chiayi County, county=10010
minxiong-hydrocast-rainfall-alerts --mode live --county 10010
```

Run rain-gauge and flood-sensor parser diagnostics:

```bash
# Demo data
minxiong-hydrocast-hydrology --mode demo

# Direct WRA monitor-page parsers for Chiayi County
minxiong-hydrocast-hydrology --mode live --county 10010 \
  --debug-dir data/raw/debug \
  --summary-output data/processed/hydrology_run_summary.json
```

Parse a local shelter DOCX file:

```bash
minxiong-hydrocast-shelters --input data/raw/shelters.docx --output data/processed/shelters.csv
```

Build a location reference table:

```bash
minxiong-hydrocast-locations \
  --rain data/processed/rain_monitor.csv \
  --flood data/processed/flood_sensors.csv \
  --output data/processed/location_reference.csv
```

Evaluate baseline models:

```bash
minxiong-hydrocast-evaluate-baselines \
  --events data/samples/flood_risk_events.csv \
  --output data/processed/baseline_evaluation.json
```

Check NowcastNet migration prerequisites:

```bash
minxiong-hydrocast-nowcastnet-smoke \
  --code-dir data/external/nowcastnet/code \
  --checkpoint data/external/checkpoints/nowcastnet_tw.pt \
  --radar-dataset data/external/radar/taiwan \
  --output data/processed/nowcastnet_smoke.json
```

Check whether a radar data source is ready for tensor conversion:

```bash
minxiong-hydrocast-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

The current CWA candidates are `O-A0059-001` for QPESUMS radar echo grids and `O-B0045-001` for
past-1-hour QPESUMS rainfall estimates. Downloads require a local `CWA_API_KEY`; keep real keys in
local env files only and keep downloaded files under ignored `data/external/` paths.

Dry-run a CWA file API download without a key or network fetch:

```bash
minxiong-hydrocast-cwa-download --dry-run --data-id O-A0059-001
```

Download a local sample after setting `CWA_API_KEY`:

```bash
export CWA_API_KEY  # set this locally first
minxiong-hydrocast-cwa-download \
  --data-id O-A0059-001 \
  --output-dir data/external/radar
```

The downloader follows CWA's documented file API pattern by sending `Authorization`, `downloadType`,
and `format` as query parameters. It redacts the key from run summaries and logs.

Inspect downloaded CWA grid samples:

```bash
minxiong-hydrocast-cwa-grid-inspect \
  data/external/radar/cwa_o_a0059_001/O-A0059-001.json \
  data/external/radar/cwa_o_b0045_001/O-B0045-001.json
```

Dry-run the inferred CWA historyAPI file-list endpoint:

```bash
minxiong-hydrocast-cwa-history-list --dry-run --data-id O-A0059-001
```

Download a specific CWA history `getData` timestamp into ignored local storage:

```bash
minxiong-hydrocast-cwa-history-data-download \
  --data-id O-A0002-001 \
  --data-time 2026-07-02T15:30:00+08:00 \
  --output data/external/gauges/events/O-A0002-001_20260702153000.xml \
  --insecure-tls
```

Use this for event-time rain-gauge captures and QPE availability probes. The downloader redacts
`Authorization` in errors, run summaries, and logs.

After the history endpoint is live-verified, build a multi-frame event plan:

```bash
minxiong-hydrocast-cwa-event-plan \
  --history-index data/processed/cwa_history_index.json \
  --event-id chiayi_20260706_evening \
  --start-time 2026-07-06T18:00:00+08:00 \
  --end-time 2026-07-06T21:00:00+08:00
```

Download the selected event frames into ignored local storage:

```bash
minxiong-hydrocast-cwa-event-plan \
  --history-index data/processed/cwa_history_index.json \
  --event-id chiayi_20260706_evening \
  --start-time 2026-07-06T18:00:00+08:00 \
  --end-time 2026-07-06T21:00:00+08:00 \
  --download \
  --download-dir data/external/radar/events \
  --collection-output data/processed/cwa_event_collection.json
```

The event plan and collection manifest keep CWA URLs redacted. The downloader reads
`CWA_API_KEY` from local environment variables only. For larger discovery scans, use
`--frame-stride` to sample frames, `--max-workers` for limited concurrent downloads, and
`--skip-existing` to resume interrupted local downloads.

Summarize a downloaded CWA event collection for local Chiayi/Minxiong and Taiwan-wide radar
threshold evidence:

```bash
minxiong-hydrocast-radar-event-summary \
  --collection data/processed/cwa_event_collection.json \
  --output data/processed/cwa_event_summary.json
```

Tracked candidate windows from the latest CWA hourly discovery scan are stored in
`data/samples/radar_event_windows.json`. They are radar-derived candidates; attach official weather
context from `data/samples/event_weather_context.json` before labeling them as typhoon, Mei-yu,
frontal, or convective events. Next-batch candidates stay in
`data/samples/event_expansion_queue.json` until they have complete 10-minute collections, tensors,
official context, and QPE/gauge validation.
Official CWA weather-context source review is tracked in
`data/samples/weather_context_source_review.json`.

Validate CWA 1-hour QPE against rain gauges after collecting local `O-B0045-001` and
`O-A0002-001` captures for the same window:

```bash
minxiong-hydrocast-qpe-gauge-validate \
  --qpe-grid data/external/radar/events/<event>/O-B0045-001.json \
  --gauge-json data/external/gauges/events/<event>/O-A0002-001.json \
  --event-id <event_id> \
  --output data/processed/qpe_gauge_validation_<event_id>.json
```

Earlier three-event source-review status is tracked in
`data/samples/qpe_gauge_validation_status.json`: `O-A0002-001` gauge captures parse for the three
events, but event-time `O-B0045-001` history `getData` probes return HTTP 404, so the actual
gauge-vs-QPE reports remain blocked until QPE grids are captured or an official archive is found.
This status file is supporting historical evidence, not the active formal split manifest.

Check event-based train/validation/test splits:

```bash
minxiong-hydrocast-event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --output data/processed/event_split_check.json
```

Convert the tiny radar-like fixture into the model tensor archive format:

```bash
minxiong-hydrocast-radar-tensor-convert \
  --source-format csv_pixel_grid \
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

Convert a CWA event collection manifest into a tensor archive:

```bash
minxiong-hydrocast-radar-tensor-convert \
  --source-format cwa_opendata_grid \
  --input data/processed/cwa_event_collection.json \
  --input-length 2 \
  --prediction-length 1 \
  --cadence-minutes 10 \
  --output data/processed/cwa_radar_tensor_sample.npz
```

For longer event windows, emit sliding-window tensors by adding `--window-stride-frames 1`.
For example, 6 input frames and 6 target frames create 10- to 60-minute lead-time samples:

```bash
minxiong-hydrocast-radar-tensor-convert \
  --source-format cwa_opendata_grid \
  --input data/processed/cwa_event_collection_taiwan_widespread_20260628_afternoon_evening.json \
  --event-id cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening \
  --input-length 6 \
  --prediction-length 6 \
  --cadence-minutes 10 \
  --window-stride-frames 1 \
  --output data/processed/cwa_tensor_taiwan_widespread_20260628_6in_6out.npz
```

Evaluate the tensor archive with the persistence baseline:

```bash
minxiong-hydrocast-tensor-baseline-evaluate \
  --archive data/processed/radar_tensor_sample.npz \
  --output data/processed/tensor_baseline_evaluation.json
```

Train the optional PyTorch baseline after installing a CUDA-enabled PyTorch build:

```bash
minxiong-hydrocast-train-torch-baseline \
  --archive data/processed/cwa_radar_tensor_sample.npz \
  --output-dir data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke \
  --device cuda \
  --multi-gpu \
  --batch-repeats 2 \
  --batch-size 1 \
  --epochs 1
```

The low-level training command masks CWA nodata values and z-score normalizes valid pixels before
computing loss. Formal experiments should use `mhc dataset-build --train-weighted-unet`, which
uses a separate validation event instead of holding out random sliding windows.

Compare the Tiny U-Net checkpoint against persistence on the same valid pixels:

```bash
minxiong-hydrocast-torch-baseline-evaluate \
  --archive data/processed/cwa_radar_tensor_sample.npz \
  --checkpoint data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke/tiny_unet_nowcaster.pt \
  --event-threshold 35 \
  --output data/processed/tiny_unet_cwa_comparison.json
```

For non-demo operation, use the live operational collector and reject any run summary whose `mode`
is `demo`. A fresh official rainfall-warning result may legitimately have zero rows when its source
outcome is `empty`; zero rain-gauge or flood-sensor rows remain an error. Every command-line
pipeline writes a JSON run summary under
`data/processed/run_summaries/` and appends a compact JSONL event to
`data/processed/run_logs.jsonl` by default. Override these with `--summary-output` and
`--log-output`, or pass `--summary-output /tmp/example.json --log-output /tmp/runs.jsonl`
for throwaway checks.

## Project Layout

```text
MinxiongHydroCast/
├── data/
│   ├── raw/          # ignored source captures
│   ├── interim/      # ignored cleaned intermediates
│   ├── processed/    # ignored validated outputs
│   ├── external/     # ignored radar/model/checkpoint assets
│   └── samples/      # tracked fixtures, manifests, and source-review evidence
├── deploy/
│   ├── prometheus/   # scrape, alert rules, and Alertmanager routing
│   ├── single-host/  # pinned installation and runner scripts
│   ├── systemd/      # system service templates
│   └── systemd-user/ # complete single-host user services and timers
├── docs/
├── scripts/
├── src/minxionghydrocast/
│   ├── ingestion/
│   ├── io/
│   ├── models/
│   ├── operations/
│   ├── pipelines/
│   ├── spatial/
│   └── validation/
└── tests/
```

## Data Safety

Do not commit credentials, cookies, private URLs, official source exports, model weights, or files
containing contact details. Use `env.example` as the template for local configuration.

## Model Direction

Start with the included baselines:

- `PersistenceNowcaster` for radar/rainfall nowcasting.
- `RainfallThresholdRiskScorer` for local threshold-based flood-risk scoring.

The best next SOTA candidate is NowcastNet, but it should be migrated only after Taiwan radar grids,
event splits, checkpoints, and licensing are clear. See [docs/model_strategy.md](docs/model_strategy.md).

Spatial alignment is documented in [docs/spatial_alignment.md](docs/spatial_alignment.md).
Baseline evaluation results are documented in [docs/baseline_results.md](docs/baseline_results.md).
The reproducible external research dataset is documented in
[docs/research_dataset.md](docs/research_dataset.md).
NowcastNet migration is documented in [docs/nowcastnet_migration.md](docs/nowcastnet_migration.md).
Radar source review is documented in [docs/radar_data_sources.md](docs/radar_data_sources.md).
Event split rules are documented in [docs/event_splits.md](docs/event_splits.md).
Radar event windows are documented in [docs/radar_event_windows.md](docs/radar_event_windows.md).
Radar tensor conversion is documented in [docs/radar_tensor_conversion.md](docs/radar_tensor_conversion.md).
Radar source adapters are documented in [docs/radar_source_adapters.md](docs/radar_source_adapters.md).
The project completion plan is documented in [docs/completion_plan.md](docs/completion_plan.md).
The Linux deployment and operations runbook is documented in
[docs/single_host_operations.md](docs/single_host_operations.md).
Current verified rollout evidence and remaining gates are recorded in
[docs/deployment_status.md](docs/deployment_status.md).
The canonical name and claims vocabulary are defined in
[docs/project_identity.md](docs/project_identity.md), and supported product boundaries are defined
in [docs/project_scope.md](docs/project_scope.md).
Operational escalation and recovery procedures are documented in
[docs/incident_response.md](docs/incident_response.md) and [docs/rollback.md](docs/rollback.md).
Decision authority and fail-closed human overrides are defined in
[docs/decision_authority.md](docs/decision_authority.md). Source purpose and rights-review status
are tracked in [docs/data_source_register.md](docs/data_source_register.md).
The current baseline model card is documented in
[docs/model_cards/minxiong_chiayi_baseline.md](docs/model_cards/minxiong_chiayi_baseline.md).
