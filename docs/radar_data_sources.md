# Radar Data Sources

MinxiongHydroCast cannot train a Taiwan-specific nowcasting model until source radar data is confirmed.
This repository tracks candidates with a manifest instead of committing raw radar files.

## Current CWA Review

Official CWA Open Data metadata was reviewed on 2026-07-06. The useful endpoints were:

- `https://opendata.cwa.gov.tw/webapi/formatType`
- `https://opendata.cwa.gov.tw/webapi/datasetPage/o`
- `https://opendata.cwa.gov.tw/webapi/datasetList/o`
- `https://opendata.cwa.gov.tw/webapi/datasetMetadata/{dataid}`
- `https://opendata.cwa.gov.tw/about/rules`

The best first radar tensor candidate is:

| Data ID | Name | Cadence | Format | Confirmed Metadata |
| --- | --- | --- | --- | --- |
| `O-A0059-001` | `雷達資料-雷達整合回波資料` | 10 min | JSON, XML, historyAPI | QPESUMS radar integrated echo grid, `dBZ` units |

The best rainfall-estimate candidate for flood-risk features is:

| Data ID | Name | Cadence | Format | Confirmed Metadata |
| --- | --- | --- | --- | --- |
| `O-B0045-001` | `降雨估計資料-QPESUMS過去1小時定量降雨估計格點資料` | 10 min | JSON, XML | QPESUMS past-1-hour radar precipitation estimate grid |

`O-A0058-001..006` are radar echo image products. Keep them as visualization/reference sources
unless sample parsing proves they preserve numeric grid values well enough for training.

The first official gauge validation source is:

| Data ID | Name | Cadence | Format | Confirmed Metadata |
| --- | --- | --- | --- | --- |
| `O-A0002-001` | `雨量觀測站-雨量資料` | observation update cadence | JSON, XML, API, historyAPI | station rainfall observations for QPE validation |

## License And Access

CWA metadata lists the license as `氣象資料開放平臺使用規範`, with the license URL
`https://opendata.cwa.gov.tw/about/rules`. The rules page references the government open data
license and attribution requirements. Treat attribution as required in derived datasets, model
cards, and reports.

CWA file downloads require an `Authorization` key. Keep real keys out of git:

```bash
cp env.example .env
# Fill CWA_API_KEY locally only.
```

Expected file API pattern:

```text
https://opendata.cwa.gov.tw/fileapi/v1/opendataapi/O-A0059-001?Authorization=${CWA_API_KEY}&downloadType=WEB&format=JSON
```

This matches CWA's OpenAPI and front-end download helper: `Authorization` is a query parameter,
not a header. No public demo key is stored in this repository. If an official demo site exposes a
public sample key, use it only for a local one-off smoke test and never commit it.

Downloaded files belong under ignored paths such as `data/external/radar/cwa_o_a0059_001/`.

## Download Command

Dry-run URL and output-path handling without a key:

```bash
minxiong-hydrocast-cwa-download --dry-run --data-id O-A0059-001
```

Download a live sample after setting a local key:

```bash
export CWA_API_KEY  # set this locally first
minxiong-hydrocast-cwa-download \
  --data-id O-A0059-001 \
  --output-dir data/external/radar
```

The command redacts `Authorization` in run summaries and logs. It fails if the output file already
exists unless `--overwrite` is passed.

Python TLS verification may reject the current CWA endpoint certificate with `Missing Subject Key
Identifier`. For local sampling only, pass `--insecure-tls`; the command still redacts the key from
its own errors and summaries.

## Sample-Verified Grid Schemas

Live JSON samples were downloaded and inspected on 2026-07-06.

| Data ID | Data Time | CRS | Origin | Resolution | Dimensions | Count | Units | Nodata |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `O-A0059-001` | `2026-07-06T19:30:00+08:00` | `TWD67` | `115.0E, 18.0N` | `0.0125 deg` | `921 x 881` | `811401` | `dBZ` | `-99`, `-999` |
| `O-B0045-001` | `2026-07-06T19:20:00+08:00` | `TWD67 lon/lat grid` | `118.0E, 20.0N` | `0.0125 deg` | `441 x 561` | `247401` | `mm` | `-1` |

Both products store comma-separated scientific-notation floats. Values are ordered from west to
east first, then south to north. Inspect local samples with:

```bash
minxiong-hydrocast-cwa-grid-inspect \
  data/external/radar/cwa_o_a0059_001/O-A0059-001.json \
  data/external/radar/cwa_o_b0045_001/O-B0045-001.json
```

## QPE/Gauge Validation

Use `O-B0045-001` only as an estimated rainfall grid until it is checked against rain gauges. Once
local QPE and `O-A0002-001` gauge captures exist, generate an ignored report:

```bash
minxiong-hydrocast-qpe-gauge-validate \
  --qpe-grid data/external/radar/events/<event>/O-B0045-001.json \
  --gauge-json data/external/gauges/events/<event>/O-A0002-001.json \
  --event-id <event_id> \
  --output data/processed/qpe_gauge_validation_<event_id>.json
```

The report uses nearest-grid lookup for the first pass and records station-level QPE, gauge
rainfall, difference, absolute error, MAE, RMSE, bias, correlation, and excluded stations. Treat
the report as validation evidence, not as a replacement for hydrology labels.

Historical three-event status is tracked in `data/samples/qpe_gauge_validation_status.json`. As of 2026-07-09,
event-time `O-A0002-001` rain-gauge captures are available and parse as CWA XML, but event-time
`O-B0045-001` history `getData` probes return HTTP 404 for all three selected radar windows. The
per-event gauge-vs-QPE reports are therefore blocked until event-time QPE grids are captured
locally or an official historical QPE archive is confirmed. This status is supporting source
evidence and does not define the current formal five-event split.

## Official Weather Context

Weather-type labels are tracked separately from radar/QPE collection because they need official
CWA evidence. The source review manifest is
`data/samples/weather_context_source_review.json`.

Reviewed CWA official pages include:

- `https://www.cwa.gov.tw/V8/C/sitemap.html`
- `https://www.cwa.gov.tw/V8/C/W/analysis.html`
- `https://www.cwa.gov.tw/V8/C/W/pdf.html`
- `https://www.cwa.gov.tw/V8/C/W/graph_collection.html`
- `https://www.cwa.gov.tw/Data/js/fcst/MFC_SFCcombo_C_Data.js`
- `https://www.cwa.gov.tw/Data/js/warn/Warning_Content.js`

The current surface-chart JS index is useful for official weather maps, but the observed current
index does not cover the selected 2026-06-28, 2026-07-02, or 2026-07-03 event windows. Direct
probes for candidate historical `SFCcombo` chart URLs for those windows returned HTTP 404; current
index control URLs returned HTTP 200, so the URL pattern is valid but the selected historical files
are not available there. Do not promote any `official_context_pending` event to front, Mei-yu,
typhoon outer rainband, or afternoon convection until another event-time source URL is verified and
recorded.

## History Workflow

CWA's front end links the history Swagger operation as
`get_v1_getMetadata__data_id_`, which implies a `GET /v1/getMetadata/{data_id}` style endpoint.
This was live-verified for `O-A0059-001` on 2026-07-08. The current client defaults to:

```text
https://opendata.cwa.gov.tw/historyapi/v1/getMetadata/{data_id}?Authorization=REDACTED
```

Dry-run the inferred URL:

```bash
minxiong-hydrocast-cwa-history-list --dry-run --data-id O-A0059-001
```

Download a specific history `getData` timestamp directly into ignored local storage:

```bash
minxiong-hydrocast-cwa-history-data-download \
  --data-id O-A0002-001 \
  --data-time 2026-07-02T15:30:00+08:00 \
  --output data/external/gauges/events/O-A0002-001_20260702153000.xml \
  --insecure-tls
```

This downloader is used for CWA rain-gauge captures and for explicit QPE availability probes. It
redacts `Authorization` from errors, summaries, and logs. CWA may return XML from history
`getData` even when the source product advertises JSON/XML formats; the QPE/gauge validator accepts
both JSON and XML gauge payloads.

After a live history index is available, create an event frame plan:

```bash
minxiong-hydrocast-cwa-event-plan \
  --history-index data/processed/cwa_history_index.json \
  --event-id chiayi_20260706_evening \
  --start-time 2026-07-06T18:00:00+08:00 \
  --end-time 2026-07-06T21:00:00+08:00
```

For broad candidate discovery, sample the history index before downloading complete 10-minute
windows:

```bash
minxiong-hydrocast-cwa-event-plan \
  --history-index data/processed/cwa_history_index_live.json \
  --event-id cwa_o_a0059_hourly_scan_20260628_20260708 \
  --start-time 2026-06-28T13:00:00+08:00 \
  --end-time 2026-07-08T12:40:00+08:00 \
  --frame-stride 6 \
  --download \
  --skip-existing \
  --max-workers 6 \
  --collection-output data/processed/cwa_event_collection_hourly_scan_20260628_20260708.json
```

Then summarize the downloaded scan:

```bash
minxiong-hydrocast-radar-event-summary \
  --collection data/processed/cwa_event_collection_hourly_scan_20260628_20260708.json \
  --output data/processed/cwa_event_summary_hourly_scan_20260628_20260708.json \
  --expected-cadence-minutes 60
```

The current tracked candidate windows and evidence are in
`data/samples/radar_event_windows.json`. Raw frames and full summaries stay under ignored
`data/external/` and `data/processed/` paths.

## Manifest

The sample manifest is `data/samples/radar_source_manifest.json`. It records:

- provider, data id, source URLs, and CWA metadata fields
- license and license URL
- access method
- native format and cadence
- projection / CRS status
- grid description
- units
- local ignored storage path
- known gaps from source review

The selected source is intentionally marked `sample_verified`; it is parseable, but it is not ready
for training until history retention and multi-frame event collection are reviewed.

## Check Command

```bash
minxiong-hydrocast-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

Use `--require-confirmed` in automation when training should fail unless the selected source is
fully reviewed:

```bash
minxiong-hydrocast-radar-source-check --require-confirmed
```

## Confirmation Criteria

Before tensor conversion or training, the selected source must have:

- `status` set to `confirmed`
- downloaded sample files inspected locally
- known native file schema
- cadence in minutes
- CRS / projection
- grid origin, extent, orientation, dimensions, and missing-value encoding
- timestamp timezone and history retention
- rainfall or reflectivity units
- reviewed license and attribution requirements
- local storage path outside git

After confirmation, update the radar tensor contract if the source does not match the provisional
`512 x 512`, 6-minute, `mm_per_hour`, `EPSG:4326` adapter spec.
