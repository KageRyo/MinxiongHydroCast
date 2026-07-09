# Data Contracts

FloodCastTW treats data contracts as the boundary between scraping, cleaning, modeling, and
product usage. Every live dataset should include source metadata and an explicit `資料模式` value.

## Rainfall Alerts

Required fields:

- `地區`
- `警戒`
- `影響村落`
- `1h雨量`
- `3h雨量`
- `6h雨量`
- `抓取時間`
- `資料模式`

## Rain Gauges

Required fields:

- `排序`
- `行政區`
- `雨量站`
- `水情時間`
- `水情時間ISO`
- `1小時累積雨量`
- `1小時累積雨量mm`
- `24小時累積雨量`
- `24小時累積雨量mm`
- `資料產出時間`
- `資料產出時間ISO`
- `抓取時間`
- `資料模式`
- `資料來源`

Future live data should add station IDs and WGS84 coordinates.

## Flood Sensors

Required fields:

- `排序`
- `縣市`
- `鄉鎮`
- `感測器名稱`
- `地址`
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

Future live data should add sensor IDs, WGS84 coordinates, and water-level units.

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

Use generated location IDs only until official station or sensor IDs are available.

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

## QPE/Gauge Validation Reports

Required top-level fields:

- `event_id`
- `qpe_source`
- `gauge_source`
- `summary`
- `matches`

Each station match should include station ID/name, coordinates, gauge rainfall, nearest QPE value,
difference, absolute error, grid row/column, status, and exclusion reason when applicable.
