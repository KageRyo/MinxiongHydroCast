# FloodCastMinxiong

[![CI](https://github.com/KageRyo/FloodCastMinxiong/actions/workflows/ci.yml/badge.svg)](https://github.com/KageRyo/FloodCastMinxiong/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Style: Ruff](https://img.shields.io/badge/style-ruff-46a6ff)](https://docs.astral.sh/ruff/)
[![Data](https://img.shields.io/badge/data-demo%20safe-orange)](data/README.md)

Minxiong-first flood-risk data pipeline and rainfall-nowcasting toolkit.

FloodCastMinxiong is a Minxiong-first flood-risk data and rainfall-nowcasting toolkit. Its
operational target is Minxiong Township, while Taiwan-wide radar data is used as upstream training
and context data. The current release is a research and data-engineering toolkit, not an official
warning system.

## What This Repo Does

- Collect WRA rainfall alert thresholds for Chiayi County.
- Ingest live rain-gauge and flood-sensor observations with explicit demo fixtures for tests.
- Parse shelter DOCX files into structured CSV without committing source documents.
- Keep raw, interim, processed, and sample data separate.
- Build stable location references for gauges, sensors, shelters, pumping stations, and risk areas.
- Provide baseline models before deep-learning training is justified.
- Prepare a `NowcastNetAdapter` boundary for future SOTA migration.
- Track official CWA radar/QPE candidate sources without committing raw downloads or API keys.

## What You Can Use Today

Today the repository is useful for four concrete workflows:

- ingest and validate live WRA rainfall-alert, rain-gauge, and flood-sensor observations;
- collect reproducible CWA radar event windows and convert them to model-ready tensors;
- benchmark persistence and Tiny U-Net nowcasting with common lead-time metrics;
- assemble Minxiong/Chiayi location references and flood-risk features for downstream systems.

It does not yet provide a continuously running service, public API, operator dashboard, or
validated public flood warning. See [docs/operational_use.md](docs/operational_use.md) for supported
operating profiles, outputs, and the gates required before public deployment.

## Quick Start

```bash
conda env create -f environment.yml
conda activate floodcast-minxiong
python -m playwright install chromium
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

Run the local demo pipeline for installation and schema checks only:

```bash
python scripts/run_demo.py
```

Run rainfall alerts:

```bash
# Demo data
floodcast-minxiong-rainfall-alerts --mode demo

# Live WRA page for Chiayi County, county=10010
floodcast-minxiong-rainfall-alerts --mode live --county 10010
```

Run rain gauge and flood-sensor ingestion:

```bash
# Demo data
floodcast-minxiong-hydrology --mode demo

# Live WRA monitor pages for Chiayi County
floodcast-minxiong-hydrology --mode live --county 10010 \
  --debug-dir data/raw/debug \
  --summary-output data/processed/hydrology_run_summary.json
```

Parse a local shelter DOCX file:

```bash
floodcast-minxiong-shelters --input data/raw/shelters.docx --output data/processed/shelters.csv
```

Build a location reference table:

```bash
floodcast-minxiong-locations \
  --rain data/processed/rain_monitor.csv \
  --flood data/processed/flood_sensors.csv \
  --output data/processed/location_reference.csv
```

Evaluate baseline models:

```bash
floodcast-minxiong-evaluate-baselines \
  --events data/samples/flood_risk_events.csv \
  --output data/processed/baseline_evaluation.json
```

Check NowcastNet migration prerequisites:

```bash
floodcast-minxiong-nowcastnet-smoke \
  --code-dir data/external/nowcastnet/code \
  --checkpoint data/external/checkpoints/nowcastnet_tw.pt \
  --radar-dataset data/external/radar/taiwan \
  --output data/processed/nowcastnet_smoke.json
```

Check whether a radar data source is ready for tensor conversion:

```bash
floodcast-minxiong-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

The current CWA candidates are `O-A0059-001` for QPESUMS radar echo grids and `O-B0045-001` for
past-1-hour QPESUMS rainfall estimates. Downloads require a local `CWA_API_KEY`; keep real keys in
local env files only and keep downloaded files under ignored `data/external/` paths.

Dry-run a CWA file API download without a key or network fetch:

```bash
floodcast-minxiong-cwa-download --dry-run --data-id O-A0059-001
```

Download a local sample after setting `CWA_API_KEY`:

```bash
export CWA_API_KEY  # set this locally first
floodcast-minxiong-cwa-download \
  --data-id O-A0059-001 \
  --output-dir data/external/radar
```

The downloader follows CWA's documented file API pattern by sending `Authorization`, `downloadType`,
and `format` as query parameters. It redacts the key from run summaries and logs.

Inspect downloaded CWA grid samples:

```bash
floodcast-minxiong-cwa-grid-inspect \
  data/external/radar/cwa_o_a0059_001/O-A0059-001.json \
  data/external/radar/cwa_o_b0045_001/O-B0045-001.json
```

Dry-run the inferred CWA historyAPI file-list endpoint:

```bash
floodcast-minxiong-cwa-history-list --dry-run --data-id O-A0059-001
```

Download a specific CWA history `getData` timestamp into ignored local storage:

```bash
floodcast-minxiong-cwa-history-data-download \
  --data-id O-A0002-001 \
  --data-time 2026-07-02T15:30:00+08:00 \
  --output data/external/gauges/events/O-A0002-001_20260702153000.xml \
  --insecure-tls
```

Use this for event-time rain-gauge captures and QPE availability probes. The downloader redacts
`Authorization` in errors, run summaries, and logs.

After the history endpoint is live-verified, build a multi-frame event plan:

```bash
floodcast-minxiong-cwa-event-plan \
  --history-index data/processed/cwa_history_index.json \
  --event-id chiayi_20260706_evening \
  --start-time 2026-07-06T18:00:00+08:00 \
  --end-time 2026-07-06T21:00:00+08:00
```

Download the selected event frames into ignored local storage:

```bash
floodcast-minxiong-cwa-event-plan \
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
floodcast-minxiong-radar-event-summary \
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
floodcast-minxiong-qpe-gauge-validate \
  --qpe-grid data/external/radar/events/<event>/O-B0045-001.json \
  --gauge-json data/external/gauges/events/<event>/O-A0002-001.json \
  --event-id <event_id> \
  --output data/processed/qpe_gauge_validation_<event_id>.json
```

Current selected-event status is tracked in
`data/samples/qpe_gauge_validation_status.json`: `O-A0002-001` gauge captures parse for the three
events, but event-time `O-B0045-001` history `getData` probes return HTTP 404, so the actual
gauge-vs-QPE reports remain blocked until QPE grids are captured or an official archive is found.

Check event-based train/validation/test splits:

```bash
floodcast-minxiong-event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --output data/processed/event_split_check.json
```

Convert the tiny radar-like fixture into the model tensor archive format:

```bash
floodcast-minxiong-radar-tensor-convert \
  --source-format csv_pixel_grid \
  --input data/samples/radar_pixels.csv \
  --output data/processed/radar_tensor_sample.npz
```

Convert a CWA event collection manifest into a tensor archive:

```bash
floodcast-minxiong-radar-tensor-convert \
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
floodcast-minxiong-radar-tensor-convert \
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
floodcast-minxiong-tensor-baseline-evaluate \
  --archive data/processed/radar_tensor_sample.npz \
  --output data/processed/tensor_baseline_evaluation.json
```

Train the optional PyTorch baseline after installing a CUDA-enabled PyTorch build:

```bash
floodcast-minxiong-train-torch-baseline \
  --archive data/processed/cwa_radar_tensor_sample.npz \
  --output-dir data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke \
  --device cuda \
  --multi-gpu \
  --batch-repeats 2 \
  --batch-size 1 \
  --epochs 1
```

The training command masks CWA nodata values and z-score normalizes valid pixels before computing
loss. For the next strong-echo experiment, add `--loss-function weighted_mse`,
`--event-threshold 35`, `--event-weight 4`, `--validation-fraction 0.2`, and
`--early-stopping-patience 3`.

Compare the Tiny U-Net checkpoint against persistence on the same valid pixels:

```bash
floodcast-minxiong-torch-baseline-evaluate \
  --archive data/processed/cwa_radar_tensor_sample.npz \
  --checkpoint data/external/checkpoints/tiny_unet_cwa_2gpu_masked_smoke/tiny_unet_nowcaster.pt \
  --event-threshold 35 \
  --output data/processed/tiny_unet_cwa_comparison.json
```

For non-demo operation, use only explicit `--mode live` commands and reject any run summary whose
`mode` is `demo`. Every command-line pipeline writes a JSON run summary under
`data/processed/run_summaries/` and appends a compact JSONL event to
`data/processed/run_logs.jsonl` by default. Override these with `--summary-output` and
`--log-output`, or pass `--summary-output /tmp/example.json --log-output /tmp/runs.jsonl`
for throwaway checks.

## Project Layout

```text
FloodCastMinxiong/
├── data/
│   ├── raw/          # ignored source captures
│   ├── interim/      # ignored cleaned intermediates
│   ├── processed/    # ignored validated outputs
│   ├── external/     # ignored radar/model/checkpoint assets
│   └── samples/      # tracked demo-safe samples
├── docs/
├── scripts/
├── src/floodcastminxiong/
│   ├── ingestion/
│   ├── io/
│   ├── models/
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
NowcastNet migration is documented in [docs/nowcastnet_migration.md](docs/nowcastnet_migration.md).
Radar source review is documented in [docs/radar_data_sources.md](docs/radar_data_sources.md).
Event split rules are documented in [docs/event_splits.md](docs/event_splits.md).
Radar event windows are documented in [docs/radar_event_windows.md](docs/radar_event_windows.md).
Radar tensor conversion is documented in [docs/radar_tensor_conversion.md](docs/radar_tensor_conversion.md).
Radar source adapters are documented in [docs/radar_source_adapters.md](docs/radar_source_adapters.md).
The project completion plan is documented in [docs/completion_plan.md](docs/completion_plan.md).
The current baseline model card is documented in
[docs/model_cards/minxiong_chiayi_baseline.md](docs/model_cards/minxiong_chiayi_baseline.md).
