# Operational Use

FloodCastMinxiong currently provides production-oriented building blocks, but it is not yet an
operational public warning service. The distinction matters: a pipeline that runs on real data is
not production-ready until freshness, failure handling, delivery, and decision ownership are
defined and monitored.

## Supported Operating Profiles

### 1. Local development and contract checks

Use `python scripts/run_demo.py` only to verify installation, schemas, logging, and output paths.
Demo output must never feed a public dashboard, notification, model evaluation, or operational
decision.

### 2. Live observation ingestion

Run the rainfall-alert and hydrology commands with explicit `--mode live`. Inspect each JSON run
summary and reject the run if its mode is not `live`, its status is not `ok`, required row counts
are zero, timestamps are stale, or validation reports contain errors.

This profile can support an internal Minxiong situational-data feed. Page-scraped WRA sources remain
fragile and should be replaced by approved official API contracts before they become a
production-critical dependency.

### 3. Historical radar dataset construction

Use the CWA history clients, event planner, grid inspector, and tensor converter to build
reproducible event datasets. Keep official raw files under ignored external storage and retain
source IDs, timestamps, checksums, grid metadata, and collection summaries.

This profile supports research, backtesting, and model development. It does not produce an
operational forecast by itself.

### 4. Baseline and neural-model evaluation

Evaluate persistence first, then compare neural checkpoints on the same event-based splits,
valid-pixel masks, thresholds, and lead times. Current Tiny U-Net results are diagnostic and do not
justify public flood-risk claims.

## Minimum Production Flow

A deployable Minxiong service should run this sequence idempotently:

1. ingest official observations and radar/QPE products;
2. validate schema, freshness, units, coordinates, and missing-data bounds;
3. write versioned raw metadata and validated records to durable storage;
4. assemble Minxiong features and generate a forecast only when all required inputs pass;
5. publish observations, experimental forecasts, and official warnings as distinct products;
6. record metrics and lineage, then alert an operator on failure or staleness.

The existing JSON run summaries and JSONL logs are the starting observability contract. They still
need a scheduler, durable storage, metrics backend, alert routing, and a serving layer.

## Production Gates

Do not present FloodCastMinxiong as an operational warning system until all gates pass:

- **Source gate:** approved WRA/CWA contracts, documented licensing, and measured retention.
- **Data gate:** freshness and quality SLOs with automated schema-drift and missing-data alarms.
- **Model gate:** independent event splits, multiple heavy-rain events, local labels, calibration,
  persistence comparison, and a published model card.
- **Service gate:** versioned API, authentication where needed, health checks, rollback, and
  reproducible deployment.
- **Operations gate:** named owners, incident response, human override, audit history, and a shadow
  deployment through at least one heavy-rain period.
- **Communication gate:** official warnings and experimental predictions are visually and
  semantically separated; uncertainty and update time are always shown.

## Recommended First Release

The first credible release should be an internal **Minxiong observation and data-quality service**,
not an automated warning product. Schedule live ingestion, expose freshness and validated station
data, retain run lineage, and alert maintainers on stale feeds. Add experimental radar nowcasts
only after the observation service is reliable; add public risk notifications only after local
backtesting and operator review.
