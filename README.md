# FloodCastTW

[![CI](https://github.com/KageRyo/FloodCastTW/actions/workflows/ci.yml/badge.svg)](https://github.com/KageRyo/FloodCastTW/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Style: Ruff](https://img.shields.io/badge/style-ruff-46a6ff)](https://docs.astral.sh/ruff/)
[![Data](https://img.shields.io/badge/data-demo%20safe-orange)](data/README.md)

Taiwan flood-risk data pipeline and nowcasting baseline toolkit.

FloodCastTW starts from Chiayi/Minxiong flood-risk use cases and is designed to grow into a
Taiwan-wide rainfall nowcasting and flood-risk platform. The current scope is data ingestion,
validation, baseline modeling, and a clean boundary for future SOTA model integration.

## What This Repo Does

- Collect WRA rainfall alert thresholds for Chiayi County.
- Produce explicit demo data for rain gauges and flood sensors while live parsers are developed.
- Parse shelter DOCX files into structured CSV without committing source documents.
- Keep raw, interim, processed, and sample data separate.
- Build stable location references for gauges, sensors, shelters, pumping stations, and risk areas.
- Provide baseline models before deep-learning training is justified.
- Prepare a `NowcastNetAdapter` boundary for future SOTA migration.

## Quick Start

```bash
conda env create -f environment.yml
conda activate floodcasttw
python -m playwright install chromium
```

Or with pip:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
```

Run the local demo pipeline:

```bash
python scripts/run_demo.py
```

Run rainfall alerts:

```bash
# Demo data
floodcasttw-rainfall-alerts --mode demo

# Live WRA page for Chiayi County, county=10010
floodcasttw-rainfall-alerts --mode live --county 10010
```

Run rain gauge and flood-sensor ingestion:

```bash
# Demo data
floodcasttw-hydrology --mode demo

# Live WRA monitor pages for Chiayi County
floodcasttw-hydrology --mode live --county 10010 \
  --debug-dir data/raw/debug \
  --summary-output data/processed/hydrology_run_summary.json
```

Parse a local shelter DOCX file:

```bash
floodcasttw-shelters --input data/raw/shelters.docx --output data/processed/shelters.csv
```

Build a location reference table:

```bash
floodcasttw-locations \
  --rain data/processed/rain_monitor.csv \
  --flood data/processed/flood_sensors.csv \
  --output data/processed/location_reference.csv
```

Evaluate baseline models:

```bash
floodcasttw-evaluate-baselines \
  --events data/samples/flood_risk_events.csv \
  --output data/processed/baseline_evaluation.json
```

Check NowcastNet migration prerequisites:

```bash
floodcasttw-nowcastnet-smoke \
  --code-dir data/external/nowcastnet/code \
  --checkpoint data/external/checkpoints/nowcastnet_tw.pt \
  --radar-dataset data/external/radar/taiwan \
  --output data/processed/nowcastnet_smoke.json
```

Check whether a radar data source is ready for tensor conversion:

```bash
floodcasttw-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

Check event-based train/validation/test splits:

```bash
floodcasttw-event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --output data/processed/event_split_check.json
```

Every command-line pipeline writes a JSON run summary under
`data/processed/run_summaries/` and appends a compact JSONL event to
`data/processed/run_logs.jsonl` by default. Override these with `--summary-output` and
`--log-output`, or pass `--summary-output /tmp/example.json --log-output /tmp/runs.jsonl`
for throwaway checks.

## Project Layout

```text
FloodCastTW/
├── data/
│   ├── raw/          # ignored source captures
│   ├── interim/      # ignored cleaned intermediates
│   ├── processed/    # ignored validated outputs
│   ├── external/     # ignored radar/model/checkpoint assets
│   └── samples/      # tracked demo-safe samples
├── docs/
├── scripts/
├── src/floodcasttw/
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
