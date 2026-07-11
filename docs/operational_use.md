# Operational Use

FloodCastMinxiong provides a runnable local observation and data-quality service, but it is not an
operational public warning service. The distinction matters: a service that runs on real data is
not production-ready until its source contracts, deployment, alert routing, decision ownership,
and shadow-operation evidence are defined and monitored.

## Run The Observation Service

Use demo mode only to verify the installation and service contract:

```bash
floodcast-minxiong-operations --mode demo --once
floodcast-minxiong-serve --host 127.0.0.1 --port 8080
```

Demo snapshots are always marked `demo` and `ready=false`; every demo dataset uses the
`demo_fixture` product type instead of an official classification. The readiness endpoint
returns HTTP 503 so demo data cannot silently satisfy a deployment health check.

Run a single live collection:

```bash
floodcast-minxiong-operations --once
```

Run continuously at a 10-minute interval:

```bash
floodcast-minxiong-operations \
  --interval-seconds 600 \
  --retention-days 30 \
  --max-age-minutes 30
```

Only one collector may write a store at a time. A process lock rejects overlapping runs and
automatically recovers when the recorded process no longer exists.

## Snapshot Storage

The default store is `data/processed/operations/`:

```text
operations/
├── latest.json
├── latest_attempt.json
└── snapshots/
    └── <snapshot-id>/
        ├── manifest.json
        └── datasets/
            ├── rainfall_alerts.csv
            ├── rain_gauges.csv
            └── flood_sensors.csv
```

Each immutable manifest records the dataset classification, fields, schema SHA-256, file SHA-256,
row count, observed time, age, freshness threshold, and schema errors. Publishing uses atomic
renames. A failed attempt receives its own error manifest and updates `latest_attempt.json`
without replacing the last readable `latest.json`.
Every status and dataset read verifies path boundaries, manifest and file checksums, schema
checksums, and CSV headers. Corrupt pointers, manifests, or datasets produce a structured
`storage_error` readiness state instead of being treated as an empty or healthy store.

Retention removes expired unreferenced snapshots. The latest readable snapshot and latest attempt
are always protected. In deployment, mount this path on durable storage with filesystem-level
backup and access control; the repository does not provide a remote object-store backend yet.

## API And Operator View

Start the localhost-only default server:

```bash
floodcast-minxiong-serve
```

The following endpoints are available:

| Endpoint | Purpose |
| --- | --- |
| `GET /healthz` | Process liveness |
| `GET /readyz` | Data readiness; returns 503 when not ready |
| `GET /metrics` | Prometheus readiness, last-attempt, dataset-age, and state metrics |
| `GET /api/v1/status` | Latest attempt, snapshot, freshness, and schema health |
| `GET /api/v1/official-alerts/rainfall` | WRA rainfall-alert source product |
| `GET /api/v1/observations/rain-gauges` | Validated WRA rain-gauge observations |
| `GET /api/v1/observations/flood-sensors` | Validated WRA flood-sensor observations |
| `GET /api/v1/shadow-readiness` | Shadow criteria, metrics, and notification blockers |
| `GET /api/v1/experimental-forecasts` | Explicit unavailable state until forecast gates pass |

The operator view at `/` presents official-source alerts, observations, and experimental
forecast availability in separate sections. The server binds to `127.0.0.1` by default. Put it
behind an authenticated reverse proxy before exposing it to another host or network.

## Shadow Deployment Gate

Copy `data/samples/shadow_evidence.example.json` outside the tracked sample directory and replace
it with reviewed heavy-rain evidence. Unconfirmed sample evidence never satisfies the gate.
Evaluate the accumulated snapshot history:

```bash
floodcast-minxiong-shadow-report \
  --evidence /var/lib/floodcast-minxiong/reviewed_shadow_evidence.json
```

The default gate requires:

- seven days of live collection history;
- at least 900 live attempts;
- at least 99% successful attempts;
- at least 95% ready attempts;
- no ready-data gap longer than 30 minutes;
- no corrupt manifests or datasets;
- at least one confirmed heavy-rain period with continuous ready coverage.

The report is atomically stored as `shadow_report.json` in the operations store and exposed by the
API and metrics endpoint. `notification_allowed` remains false even when the shadow criteria pass,
because notification delivery and local model-label gates are separate unfinished requirements.

## Linux Service Supervision

Templates under `deploy/systemd/` provide:

- a hardened one-shot live collector service;
- a persistent timer that runs every 10 minutes and catches up after downtime;
- a restartable localhost API service.

The templates assume:

- the repository and virtual environment are installed under `/opt/floodcast-minxiong`;
- a non-login `floodcast-minxiong` service user and group exist;
- local secrets and endpoint overrides are stored in `/etc/floodcast-minxiong.env`;
- durable snapshots and run state live under `/var/lib/floodcast-minxiong`.

Review paths, users, filesystem permissions, browser dependencies, and reverse-proxy policy before
installation. Prefer the systemd timer over the in-process interval loop on a single Linux host,
because the timer records each attempt independently and uses `Persistent=true` after downtime.
Install Playwright Chromium into the path configured by the collector unit before enabling it:

```bash
PLAYWRIGHT_BROWSERS_PATH=/opt/floodcast-minxiong/.playwright \
  /opt/floodcast-minxiong/.venv/bin/python -m playwright install chromium
```

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

The scheduler, local versioned store, health/readiness contract, JSON run summaries, JSONL logs,
Prometheus metrics endpoint, read API, and operator view are implemented. Production deployment
still needs a durable mounted volume or object-store backend, metrics scraping and alert rules,
alert routing, authentication, and service supervision.

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

The first credible release remains an internal **Minxiong observation and data-quality service**,
not an automated warning product. The repository now supplies the runnable service foundation.
The next deployment work is to mount durable storage, supervise both processes, export metrics,
route stale/failure alerts to named maintainers, and complete a shadow run. Add experimental radar
nowcasts only after the observation service is reliable; add public risk notifications only after
local backtesting and operator review.
