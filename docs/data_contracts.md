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

- `測站`
- `時間`
- `1H雨量`
- `累積雨量`
- `狀態`
- `抓取時間`
- `資料模式`

Future live data should add station IDs and WGS84 coordinates.

## Flood Sensors

Required fields:

- `測站`
- `水位`
- `狀態`
- `抓取時間`
- `資料模式`

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
