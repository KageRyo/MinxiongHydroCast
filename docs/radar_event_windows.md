# Radar Event Windows

This document tracks CWA `O-A0059-001` radar windows selected for dataset building. Raw CWA frames,
collections, summaries, tensor archives, and checkpoints stay in ignored `data/external/` and
`data/processed/` paths.

## Discovery Scan

The current discovery scan used the 2026-07-08 live history index:

- History range: `2026-06-28T13:00:00+08:00` to `2026-07-08T12:40:00+08:00`
- History files: 1439
- Scan event: `cwa_o_a0059_hourly_scan_20260628_20260708`
- Scan cadence: hourly, via `--frame-stride 6`
- Scan frames: 240
- Threshold: `35.0 dBZ`

Summarize a scan or collection with:

```bash
floodcasttw-radar-event-summary \
  --collection data/processed/cwa_event_collection_hourly_scan_20260628_20260708.json \
  --output data/processed/cwa_event_summary_hourly_scan_20260628_20260708.json \
  --expected-cadence-minutes 60
```

## Candidate Windows

Candidate evidence is tracked in `data/samples/radar_event_windows.json`.

| Event ID | Region | Full Window To Collect | Evidence |
| --- | --- | --- | --- |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon` | Minxiong, Chiayi | `2026-07-02T12:00:00+08:00` to `2026-07-02T18:00:00+08:00` | local peak `58.0 dBZ` at `15:00` |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | Minxiong, Chiayi | `2026-07-03T13:00:00+08:00` to `2026-07-03T19:00:00+08:00` | local coverage peak: 198 pixels >= `35 dBZ` |
| `cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening` | Taiwan | `2026-06-28T13:00:00+08:00` to `2026-06-28T21:00:00+08:00` | Taiwan coverage peak: 6498 pixels >= `35 dBZ` |

These are radar-derived labels only. Attach official weather context before naming a window
typhoon, Mei-yu, frontal, or convective.

## Full Collection Commands

Use the same command shape for each selected window:

```bash
floodcasttw-cwa-event-plan \
  --history-index data/processed/cwa_history_index_live.json \
  --event-id cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon \
  --start-time 2026-07-02T12:00:00+08:00 \
  --end-time 2026-07-02T18:00:00+08:00 \
  --download \
  --download-dir data/external/radar/events \
  --collection-output data/processed/cwa_event_collection_chiayi_minxiong_heavyrain_20260702_afternoon.json \
  --skip-existing \
  --max-workers 6 \
  --insecure-tls
```

After each full collection, rerun `floodcasttw-radar-event-summary` with the default
`--expected-cadence-minutes 10`, then convert longer sequences to tensor archives for lead-time
metrics.
