# WRA IoW Freshness Evidence

This note records the 2026-09-12 freshness investigation for the WRA IoW flood-depth product. It
is public-safe: it contains no API key, host path, raw payload, or private deployment identifier.

## Source contract

The government catalog entry for [IoW淹水深度最新資料, dataset
142980](https://data.gov.tw/dataset/142980) identifies `sensorid`, `latestvalue`, and `timestamp`
as the measurement fields and documents an hourly update frequency (`每1時`). The public WRA JSON
resource is the feed joined by the adapter with sensor metadata from dataset 142979.

## Observed run

On 2026-09-12, the scheduled official-contract check fetched the WRA feed successfully:

| Check | Observation |
| --- | --- |
| HTTP/adapter result | Valid response; 150 joined records; no parser or authentication error |
| CWA companion contract | 83 rain-gauge records, `outcome=ok` |
| WRA newest observation | `2026-09-02T12:25:46+08:00` in the local normalized snapshot |
| Fetch behavior | Later fetches advanced, but the WRA source-content SHA-256 remained unchanged |
| Freshness policy | `max_age_minutes=90` |
| Result | `outcome=stale`, readiness false, scheduled contract failed closed |

The public resource currently exposes timestamps with an explicit `+08:00` offset, and the adapter
requires timezone-aware timestamps before converting them to Asia/Taipei. The timestamp therefore
does not indicate a naive-time parsing bug. The observed state is an unchanged upstream snapshot
whose age is far beyond the nominal hourly cadence.

## Decision

Keep the 90-minute threshold unchanged. Do not classify a successful HTTP response as fresh merely
because it contains rows, and do not substitute WRA river-level dataset 25768 for the flood-depth
product. Continue recording fetch time, newest observation time, source checksum, row count, and
outcome for each attempt.

## Follow-up

If the same stale observation persists across subsequent scheduled attempts, compare the public
dataset's publication timestamp and update cadence with the adapter's parsed observation timestamp.
Only a confirmed contract change should lead to a reviewed threshold or timestamp-semantics change;
otherwise the fail-closed stale result is the expected safety behavior.
