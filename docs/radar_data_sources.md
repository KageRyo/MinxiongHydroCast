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
| `O-A0059-001` | `雷達資料-雷達整合回波資料` | 10 min | JSON, XML, historyAPI | QPESUMS radar integrated echo grid, 1.25 km resolution, `dBZ` units |

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

Downloaded files belong under ignored paths such as `data/external/radar/cwa_o_a0059_001/`.

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

The selected source is intentionally still marked `candidate`; it is not ready for training.

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
