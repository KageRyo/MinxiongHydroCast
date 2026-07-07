# Radar Data Sources

FloodCastTW cannot train a Taiwan-specific nowcasting model until source radar data is confirmed.
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
floodcasttw-cwa-download --dry-run --data-id O-A0059-001
```

Download a live sample after setting a local key:

```bash
export CWA_API_KEY  # set this locally first
floodcasttw-cwa-download \
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
floodcasttw-cwa-grid-inspect \
  data/external/radar/cwa_o_a0059_001/O-A0059-001.json \
  data/external/radar/cwa_o_b0045_001/O-B0045-001.json
```

## History Workflow

CWA's front end links the history Swagger operation as
`get_v1_getMetadata__data_id_`, which implies a `GET /v1/getMetadata/{data_id}` style endpoint.
The current client defaults to:

```text
https://opendata.cwa.gov.tw/historyapi/v1/getMetadata/{data_id}?Authorization=REDACTED
```

This endpoint still needs live verification against CWA because the official history Swagger JS was
not available during the last offline implementation pass.

Dry-run the inferred URL:

```bash
floodcasttw-cwa-history-list --dry-run --data-id O-A0059-001
```

After a live history index is available, create an event frame plan:

```bash
floodcasttw-cwa-event-plan \
  --history-index data/processed/cwa_history_index.json \
  --event-id chiayi_20260706_evening \
  --start-time 2026-07-06T18:00:00+08:00 \
  --end-time 2026-07-06T21:00:00+08:00
```

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
floodcasttw-radar-source-check \
  --manifest data/samples/radar_source_manifest.json \
  --output data/processed/radar_source_check.json
```

Use `--require-confirmed` in automation when training should fail unless the selected source is
fully reviewed:

```bash
floodcasttw-radar-source-check --require-confirmed
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
