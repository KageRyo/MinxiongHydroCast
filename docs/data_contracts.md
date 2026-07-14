# Data Contracts

MinxiongHydroCast treats data contracts as the boundary between upstream collection, cleaning,
modeling, and product usage. Every live dataset includes source metadata and an explicit
`資料模式` value. Operational collection prefers official machine-readable sources; a page scraper
is only a degraded request-failure fallback.

## Research Dataset Artifacts

The formal radar research manifest is validated by a strict Pydantic schema before any event is
downloaded. It requires exactly event-based train, validation, and test splits with minimum real
event counts of 2/1/2, including two held-out Minxiong test events. Demo IDs and sources,
unassigned events, duplicate assignment, invalid timestamps, and unknown fields fail the build.

CWA history indexes, event plans, collection manifests, Persistence evaluations, Tiny U-Net
training and comparison reports, the dataset catalog, and the checksum verification report are
also validated through Pydantic before JSON serialization. The external catalog records relative
artifact paths, byte sizes, SHA-256, provenance, event time ranges, and aggregate and lead-time
metrics. Artifact resolution rejects absolute research paths and attempts to escape the configured
research root. See [research_dataset.md](research_dataset.md).

## Event Evidence Catalog

`EventEvidenceCatalog` is the strict boundary for continuous radar discovery. It stores the
incremental cursor, immutable discovery configuration, checksummed history indexes, candidate
trigger metrics, full radar-window artifacts, and synchronized QPE/gauge/warning captures. Unknown
fields, naive timestamps, duplicate candidates or trigger times, inconsistent frame counts, and
artifact paths outside the research root fail validation.

Discovery configuration includes a cadence-aligned maximum candidate window, defaulting to 480
minutes and including the before/after context. A trigger that would exceed the bound starts a new
candidate. Older catalogs without the field parse with that default; an already overlong candidate
is preserved instead of being rewritten.

Every candidate is constrained to `candidate_only` with `formal_split_membership=not_added`.
Catalogs require `automatic_formal_split_updates=false` and
`retraining_policy=only_after_human_approved_new_events`. A complete frame window can only become
`awaiting_review`; it cannot become a formal dataset event through discovery. See
[continuous_event_evidence.md](continuous_event_evidence.md).

An `approved` candidate additionally requires a Pydantic `EventReviewRecord` with reviewer identity,
timezone-aware review time, a classified weather regime, official HTTPS context references,
checksummed `OfficialContextArtifact` records, and a complete synchronized QPE/gauge/warning
capture. Each official-context record preserves publisher, source URL, published and fetched times,
and an external artifact path, byte size, and SHA-256. The formal manifest must reference its origin
with `evidence_candidate_id`. `event-split-check` and `dataset-build` share one gate that verifies
all external catalog checksums and rejects any candidate whose approval, source data ID, time
window, or reviewed regime does not match the formal event. The build runs this gate before source
downloads or model training.

## Rainfall Alerts

Required fields:

- `雨量站代碼`
- `縣市代碼`
- `鄉鎮代碼`
- `地區`
- `水情時間`
- `水情時間ISO`
- `警戒`
- `警戒級別`
- `影響村落`
- `10分鐘雨量mm`
- `1小時雨量mm`
- `3小時雨量mm`
- `6小時雨量mm`
- `12小時雨量mm`
- `24小時雨量mm`
- `抓取時間`
- `資料模式`
- `資料來源`

The primary source is the WRA OpenApiv3 `GET /v2/Rainfall/Warning` contract. The API key is sent
only in the `apikey` request header. Its top-level `UpdataTime` and `Data` payload, warning fields,
numeric ranges, and timestamps are validated with strict Pydantic schemas; missing, unexpected, or
wrongly typed fields are schema drift and fail the collection without scraper fallback.

This product contains only warnings that are currently in effect. A validated response with
`Data=[]` is therefore a successful no-active-warning result, represented by zero records and
`outcome=empty`. The collector uses its fetch time for freshness, so a fresh official empty result
is `healthy` and ready. It must not be converted into an error row or a fabricated "no warning"
record.

## Rain Gauges

Required fields:

- `排序`
- `行政區`
- `雨量站`
- `雨量站代碼`
- `水情時間`
- `水情時間ISO`
- `1小時累積雨量`
- `1小時累積雨量mm`
- `24小時累積雨量`
- `24小時累積雨量mm`
- `緯度`
- `經度`
- `資料產出時間`
- `資料產出時間ISO`
- `抓取時間`
- `資料模式`
- `資料來源`

The CWA `O-A0002-001` adapter populates the official station ID and WGS84 coordinates. Scraper
fallback records retain these fields as empty rather than fabricating identifiers or coordinates.

## Operational Source Provenance

Every immutable operational dataset records:

- `source_kind`: `api`, `scraper_fallback`, or `demo_fixture`
- `outcome`: `ok`, `empty`, `stale`, or `fallback`
- `authority`
- `dataset_id`
- `source_url` with credentials redacted
- `fetched_at`
- `schema_version`
- `content_sha256`
- optional `fallback_reason_kind` and `fallback_reason`

`scraper_fallback` datasets are always degraded and never ready. Expected empty API products must
use the explicit `empty` outcome; unexpected empty observation datasets fail the collection.

In `auto` source mode, only authentication, transport, HTTP, timeout, and rate-limit request
failures can invoke a scraper fallback. Upstream Pydantic schema drift, invalid timestamps, unit
changes, join failures, and unexpected empty observation sets fail closed.

## Flood Sensors

Required fields:

- `排序`
- `感測器代碼`
- `觀測站代碼`
- `縣市代碼`
- `鄉鎮代碼`
- `縣市`
- `鄉鎮`
- `感測器名稱`
- `觀測站名稱`
- `維運單位`
- `類別`
- `地址`
- `緯度`
- `經度`
- `啟用狀態`
- `水情時間`
- `水情時間ISO`
- `目前感測值`
- `目前感測值數值`
- `目前感測值單位`
- `資料產出時間`
- `資料產出時間ISO`
- `抓取時間`
- `資料模式`
- `資料來源`

The official adapter joins the WRA IoW latest flood-depth measurements from government Open Data
dataset [142980](https://data.gov.tw/dataset/142980) with sensor metadata from dataset
[142979](https://data.gov.tw/dataset/142979) by `sensorid`. It requires matching county/town codes,
official observatory identifiers, WGS84 coordinates, enabled state, category `淹水深度`, and unit
`cm`. A measurement without matching metadata, duplicate sensor IDs, conflicting location codes,
negative target depth, or an unexpected empty target set fails closed as an upstream contract
error. Dataset 142979 does
not provide a street address, so official API records leave `地址` empty instead of fabricating one.
Disabled sensors remain in the source dataset for auditability but do not contribute to the
Minxiong feature or determine source freshness; a target with no enabled sensor is not ready.

These endpoints are official public Open Data snapshots updated approximately hourly. They are not
the bearer-protected, station-origin real-time feed, so the operational freshness threshold is 90
minutes and the service must not claim sub-hour sensor latency. The source can be official and
healthy while still having a slower publication cadence than the original measuring station.

## River Water Levels

Government Open Data dataset [25768](https://data.gov.tw/dataset/25768) contains river and regional
drainage water-level observations. It is not a street/community flood-depth sensor product, and its
records are not fully quality-controlled. MinxiongHydroCast therefore does not map it into
`flood_sensors`, derive Minxiong flood-sensor features from it, or expose it as an operational
dataset today. A future integration must use a separate `river_water_levels` contract and retain
the upstream `checkresult`, `checkdesc`, observation timestamp, and explicit freshness state.

## Minxiong Feature Coverage

The derived `minxiong_features` row includes `coverage_ready` and `coverage_gaps`. Live readiness
requires at least one Minxiong rain gauge and one enabled Minxiong flood-depth sensor. A healthy
Chiayi County feed with no Minxiong records is `coverage_missing`, not ready. A valid empty rainfall
warning remains healthy and contributes an alert count of zero; it is not a coverage gap.

## Shelters

Required fields:

- `鄉鎮市`
- `避難所名稱`
- `避難所地址`
- `避難所聯絡人`
- `收容人數`
- `來源檔案`
- `抽取時間`

Shelter source files often include contact information. Keep real exports in `data/raw/` and do
not commit them without a privacy review.

## Location Reference

Required fields:

- `location_id`
- `source_type`
- `source_name`
- `county`
- `township`
- `village`
- `address`
- `latitude`
- `longitude`
- `crs`
- `coordinate_source`
- `admin_unit_key`

`location_id` remains a snapshot-stable derived hash. Keep the official station and sensor IDs in
their source datasets for authoritative cross-system joins; do not present the derived hash as a
WRA or CWA identifier.

## Grid Specs

Required fields:

- `name`
- `crs`
- `west`
- `south`
- `east`
- `north`
- `resolution_degrees`
- `rows`
- `cols`
- `description`

Grid cells should be referenced by stable cell IDs from `GridSpec.cell_id()`.

## Event Weather Context

Required fields in `data/samples/event_weather_context.json`:

- `event_id`
- `window_start`
- `window_end`
- `radar_candidate_type`
- `official_weather_type`
- `official_evidence`
- `minimum_required_evidence`
- `status`

Use `official_context_pending` until CWA weather maps, warnings, daily reports, or equivalent
official sources are attached.

## Weather Context Source Review

Required top-level fields in `data/samples/weather_context_source_review.json`:

- `schema_version`
- `verified_at`
- `official_sources_reviewed`
- `events`
- `next_actions`

Each event entry should include `event_id`, `official_weather_type`, `label_status`,
`needed_sources`, and `next_probe_urls`. Use a `blocked_*` label status until an event-time CWA
weather map, warning, daily report, or equivalent official product is attached.

## QPE/Gauge Validation Reports

Required top-level fields:

- `event_id`
- `qpe_source`
- `gauge_source`
- `summary`
- `matches`

Each station match should include station ID/name, coordinates, gauge rainfall, nearest QPE value,
difference, absolute error, grid row/column, status, and exclusion reason when applicable.

## QPE/Gauge Validation Status

Required top-level fields in `data/samples/qpe_gauge_validation_status.json`:

- `schema_version`
- `verified_at`
- `required_products`
- `availability_findings`
- `events`
- `next_actions`

Each event status should include `event_id`, `validation_time`, `gauge_status`, gauge station
counts, `qpe_status`, a redacted QPE endpoint, and `report_status`. Use
`blocked_missing_event_time_qpe_grid` until a matching `O-B0045-001` QPE grid exists for that
event time.
