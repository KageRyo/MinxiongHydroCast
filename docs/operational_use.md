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

Run a single live collection. The collector reads process environment variables and does not
auto-load `.env`; keep the local file ignored and source it before starting the process:

```bash
set -a
source .env
set +a

floodcast-minxiong-operations --once \
  --alert-source auto \
  --rain-source auto \
  --flood-source auto \
  --flood-max-age-minutes 90
```

Primary live collection requires `WRA_API_KEY` and `CWA_API_KEY` in the environment. Never pass
either value on the command line, store it in a tracked file, or include it in a source URL.

The three selectors `--alert-source`, `--rain-source`, and `--flood-source` each accept `api`,
`auto`, or `scraper`:

- rainfall warnings use WRA OpenApiv3 `GET /v2/Rainfall/Warning`; `WRA_API_KEY` is sent in the
  `apikey` request header;
- rain gauges use the official CWA `O-A0002-001` REST API with `CWA_API_KEY`;
- flood-depth sensors join WRA IoW government Open Data dataset
  [142980](https://data.gov.tw/dataset/142980) latest measurements to
  [142979](https://data.gov.tw/dataset/142979) sensor metadata by `sensorid`.

`auto` permits the corresponding WRA page fallback only for authentication, timeout, transport,
HTTP, or rate-limit request failures. Any fallback dataset is explicitly `degraded`, records the
request-failure reason, and cannot pass readiness. `api` makes request failures fatal; `scraper` is
for an explicitly managed source incident. Strict upstream Pydantic schema drift, invalid
timestamps or units, broken IoW joins, and unexpected empty observation sets always fail closed
without scraper fallback.

The rainfall-warning API publishes only active warnings. A schema-valid `Data=[]` response means
that no matching warning is in effect: it produces zero rows with `outcome=empty`, uses the fetch
time for freshness, and is healthy while fresh. Rain-gauge and flood-sensor empty sets are not
expected and remain collection errors.

WRA IoW 142980/142979 is an official public snapshot updated approximately hourly. It is not the
bearer-protected, station-origin real-time API, so `--flood-max-age-minutes` defaults to 90. Do not
promise sub-hour sensor latency from this source. Disabled sensors remain visible in the source
dataset for audit purposes but are excluded from the Minxiong feature and freshness decision.

WRA government Open Data dataset [25768](https://data.gov.tw/dataset/25768) is a different product:
it reports river and regional-drainage water levels, and its observations are not fully
quality-controlled. It is not a substitute for street/community flood-depth sensors. The collector
does not ingest it into `flood_sensors` or operational features; a future integration must publish a
separate `river_water_levels` dataset retaining `checkresult`, `checkdesc`, timestamps, and
freshness.

Validate all three official observation contracts independently of Chromium:

```bash
floodcast-minxiong-cwa-rain-smoke --county 10010 --county-name 嘉義縣
floodcast-minxiong-wra-alert-smoke --county 10010
floodcast-minxiong-wra-flood-smoke --county 10010
```

Run continuously at a 10-minute interval:

```bash
floodcast-minxiong-operations \
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
            ├── flood_sensors.csv
            ├── minxiong_features.csv
            └── location_reference.csv
```

Each immutable manifest records the dataset classification, fields, schema SHA-256, file SHA-256,
row count, observed time, age, freshness threshold, and schema errors. Publishing uses atomic
renames. A failed attempt receives its own error manifest and updates `latest_attempt.json`
without replacing the last readable `latest.json`.
Each dataset also records source provenance: `source_kind`, outcome, authority, dataset ID,
redacted source URL, fetch time, adapter schema version, raw-content checksum, and fallback reason.
The API exposes the same provenance with its dataset response.
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
| `GET /metrics` | Prometheus readiness, attempt, age, state, source-kind, and outcome metrics |
| `GET /api/v1/status` | Latest attempt, snapshot, freshness, and schema health |
| `GET /api/v1/official-alerts/rainfall` | WRA rainfall-alert source product |
| `GET /api/v1/observations/rain-gauges` | Validated CWA rain-gauge observations |
| `GET /api/v1/observations/flood-sensors` | Validated WRA IoW flood-depth snapshots |
| `GET /api/v1/features/minxiong` | Derived Minxiong township feature contract |
| `GET /api/v1/locations` | Snapshot-aligned operational location reference |
| `GET /api/v1/shadow-readiness` | Shadow criteria, metrics, and notification blockers |
| `GET /api/v1/experimental-forecasts` | Explicit unavailable state until forecast gates pass |

All JSON responses are validated and serialized through the Pydantic models in
`floodcastminxiong.operations.schemas`. Fixed response fields reject unknown keys and invalid
types; dataset responses also require `row_count` to match the number of returned records. The
source-specific columns inside each record remain dynamic strings because the endpoint exposes
multiple separately versioned tabular contracts.

The operator view at `/` presents official-source alerts, observations, and experimental
forecast availability in separate sections. The server binds to `127.0.0.1` by default. Put it
behind an authenticated reverse proxy before exposing it to another host or network.

## Minxiong Feature Contract

Every successful snapshot derives one Minxiong township feature row from the same immutable source
records. It contains stable rain-gauge and flood-sensor location IDs, latest observation times,
maximum 1-hour/24-hour station rainfall, normalized maximum sensor water level, rainfall-alert
counts, and upstream health states.

The feature is marked ready only when every upstream live dataset is healthy and the snapshot has
at least one Minxiong rain gauge plus one enabled Minxiong flood-depth sensor. The
`coverage_ready` and `coverage_gaps` fields distinguish missing township coverage from a healthy
county-wide feed. It never substitutes missing products: `qpe_available=false`, an empty QPE accumulation, and
`experimental_forecast_included=false` remain explicit until those sources pass their own gates.
Demo snapshots classify the feature as `demo_fixture`. A healthy empty rainfall-warning input
contributes an alert count of zero and does not block the feature; an empty observation input does.

Current rain gauges and flood sensors always produce stable location references from the same
snapshot. Optional processed pumping-station, shelter, and flood-risk-area CSVs can be supplied to
the collector. They are copied into the immutable location reference rather than read dynamically
by the API, so every feature ID resolves against the same snapshot version.

## Shadow Deployment Gate

Copy `data/samples/shadow_evidence.example.json` outside the tracked sample directory and replace
it with reviewed heavy-rain evidence. Unconfirmed sample evidence never satisfies the gate.
Evaluate the accumulated snapshot history:

```bash
floodcast-minxiong-shadow-report \
  --evidence /var/lib/floodcast-minxiong/reviewed_shadow_evidence.json
```

The default gate requires:

- seven days of live collection history measured inside an eight-day audit window;
- at least 900 live attempts;
- at least 99% successful attempts;
- at least 95% ready attempts;
- no ready-data gap longer than 30 minutes;
- no corrupt manifests or datasets;
- at least one confirmed heavy-rain period with continuous ready coverage.

The report is atomically stored as `shadow_report.json` in the operations store and exposed by the
API and metrics endpoint. `notification_allowed` remains false even when the shadow criteria pass,
because notification delivery and local model-label gates are separate unfinished requirements.

## Local Flood Labels

Real Minxiong flood labels must be kept outside tracked demo data. Start from
`data/samples/flood_labels.example.json`, replace every placeholder with reviewed evidence, and
audit the result:

```bash
floodcast-minxiong-label-audit \
  --manifest /var/lib/floodcast-minxiong/reviewed_flood_labels.json \
  --output /var/lib/floodcast-minxiong/flood_label_audit.json \
  --require-training-ready
```

Confirmed labels require a unique event ID, a non-overlapping Minxiong time window, a boolean
observed outcome, an allowed evidence type, a source reference, and reviewer identity/time. The
default model-training gate requires 10 positive and 20 negative confirmed events. Unconfirmed
examples and demo threshold events do not count.

## Linux Service Supervision

System-level templates under `deploy/systemd/` provide the basic collector and API services.
The executable single-host profile under `deploy/systemd-user/` and `deploy/single-host/` adds:

- a one-shot live collector with a persistent 10-minute timer;
- a restartable localhost API and operator view;
- Prometheus rules, Alertmanager, and a durable local notification audit receiver;
- daily checksummed backups and an explicit restore command;
- hourly shadow-gate evaluation;
- a dedicated self-hosted runner for the host-bound WRA warning contract.

The single-host installer uses:

- `/mnt/8tb_hdd/ryo/floodcast-minxiong` for durable mutable state;
- `~/.local/share/floodcast-minxiong` as a stable runtime symlink;
- `~/.config/floodcast-minxiong/env` with mode `0600` for `CWA_API_KEY` and `WRA_API_KEY`;
- user-level systemd supervision, with login linger enabled for service persistence.

See [single_host_operations.md](single_host_operations.md) for installation, validation, alert
drill, backup/restore drill, runner setup, and shadow evidence procedures. The system-level
templates remain available when a dedicated service account and `/var/lib` layout are preferred.

The scheduled `.github/workflows/cwa-live-contract.yml` workflow, named `Official Live Contracts`,
exercises the official CWA rain, WRA rainfall-warning, and WRA IoW contracts. Configure the
repository secrets `CWA_API_KEY` and `WRA_API_KEY`; the workflow fails explicitly when a required
secret is absent and never prints either key or an unredacted credential-bearing request. CWA and
IoW run on GitHub-hosted infrastructure. The WRA warning job uses the dedicated host label because
the credential can be constrained by source host.

Prefer the systemd timer over the in-process interval loop on a single Linux host, because the
timer records each attempt independently and uses `Persistent=true` after downtime. The deployed
profile selects strict official API sources and therefore does not require a Playwright browser.

## Supported Operating Profiles

### 1. Local development and contract checks

Use `python scripts/run_demo.py` only to verify installation, schemas, logging, and output paths.
Demo output must never feed a public dashboard, notification, model evaluation, or operational
decision.

### 2. Live observation ingestion

Run `floodcast-minxiong-operations` with live mode and the three source selectors. Inspect each JSON
run summary and reject the run if its mode is not `live`, its status is not `ok`, observations are
empty or stale, or validation reports contain errors. A rainfall-warning row count of zero is valid
only when its official source provenance says `outcome=empty`.

This profile can support an internal Minxiong situational-data feed. Its primary observation inputs
are official APIs/Open Data; any page-scraped fallback is visible as degraded and not ready. That
makes the project more than a demo, but does not satisfy the deployment, operations, evidence, and
public-communication gates below.

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
Prometheus metrics endpoint, read API, operator view, monitoring configs, local alert audit,
checksummed backup/restore tooling, and single-host installation scripts are implemented. Promotion
still requires a healthy managed-host rollout, a named human alert channel, an off-host backup,
authenticated network exposure if needed, and completion of the shadow and model evidence gates.

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

The immediate blockers are concrete:

- finish and verify the supplied managed-host deployment with least-privilege secret delivery;
- add a named human receiver for failed, stale, degraded, and schema alerts, then exercise the
  incident path; the durable localhost audit receiver alone is insufficient;
- add an off-host backup target after verifying the local scheduled backup and restore drill;
- complete the seven-day shadow gate with at least 900 attempts, 99% collection success, 95%
  readiness, no gap over 30 minutes, and continuous coverage of at least one reviewed heavy-rain
  period;
- document decision ownership, incident response, human override, and rollback before enabling
  any notification.

## Recommended First Release

The first credible release remains an internal **Minxiong observation and data-quality service**,
not an automated warning product. The repository supplies the runnable service and operations
foundation. The remaining promotion work is to verify the host deployment, add off-host recovery
and a named human alert route, and complete the real shadow run. Add experimental radar nowcasts
only after the observation service is reliable; add public risk notifications only after local
backtesting and operator review.
