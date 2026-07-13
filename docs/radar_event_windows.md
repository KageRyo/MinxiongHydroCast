# Historical Radar Event Windows

This document preserves the earlier three-event discovery and experiment record. It is not the
active formal split. The current five-event manifest, durable external research layout, build
command, checksums, and independent validation/test results are documented in
[research_dataset.md](research_dataset.md) and [event_splits.md](event_splits.md).

The historical raw CWA frames, collections, summaries, tensor archives, and checkpoints stay in
ignored paths and must not be committed.

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
minxiong-hydrocast-radar-event-summary \
  --collection data/processed/cwa_event_collection_hourly_scan_20260628_20260708.json \
  --output data/processed/cwa_event_summary_hourly_scan_20260628_20260708.json \
  --expected-cadence-minutes 60
```

## Candidate Windows

Candidate evidence is tracked in `data/samples/radar_event_windows.json`.
Next-batch queued windows from the same hourly scan are tracked in
`data/samples/event_expansion_queue.json`; they are not part of train/validation/test until full
10-minute collections, official weather context, tensors, and validation reports exist.

| Event ID | Split | Region | Full Window | Evidence |
| --- | --- | --- | --- | --- |
| `cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening` | train | Taiwan | `2026-06-28T13:00:00+08:00` to `2026-06-28T21:00:00+08:00` | Taiwan coverage peak: 7244 pixels >= `35 dBZ` in the full 10-minute sequence |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon` | test | Minxiong, Chiayi | `2026-07-02T12:00:00+08:00` to `2026-07-02T18:00:00+08:00` | local peak `58.8 dBZ` at `15:30` |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | test | Minxiong, Chiayi | `2026-07-03T13:00:00+08:00` to `2026-07-03T19:00:00+08:00` | local coverage peak: 198 pixels >= `35 dBZ` |

These are radar-derived labels only. Attach official weather context before naming a window
typhoon, Mei-yu, frontal, or convective.

Official weather-context tracking lives in `data/samples/event_weather_context.json`. The current
entries are intentionally `official_context_pending`; do not stratify train/test by weather type
until each event cites CWA weather maps, warnings, daily reports, or another official source.
Official source review and next CWA probe URLs are tracked in
`data/samples/weather_context_source_review.json`.

Current official-source review found CWA pages for weather warnings, typhoon warnings, weather
overview PDFs, analysis charts, and latest chart graphics. The CWA surface chart JS listed recent
charts from `2026-07-06T20:00:00+08:00` through `2026-07-09T14:00:00+08:00`, which does not cover
the three selected event windows. Direct probes for candidate `SFCcombo` chart URLs on 2026-06-28,
2026-07-02, and 2026-07-03 returned HTTP 404, while current-index control URLs returned HTTP 200.
The events therefore remain `official_context_pending` until another CWA event-time source is
found.

## QPE/Gauge Status

QPE/gauge availability tracking lives in `data/samples/qpe_gauge_validation_status.json`.
Event-time CWA `O-A0002-001` gauge captures are available locally and parse as XML. Event-time
CWA `O-B0045-001` QPE history `getData` probes returned HTTP 404 for all three selected windows,
so gauge-vs-QPE reports are blocked until QPE grids are captured or an official archive is found.

| Event ID | Validation Time | Gauge Stations | Gauge Stations >= 10 mm | QPE Status |
| --- | --- | ---: | ---: | --- |
| `cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening` | `2026-06-28T13:30:00+08:00` | 1287 | 3 | blocked: `O-B0045-001` history getData HTTP 404 |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon` | `2026-07-02T15:30:00+08:00` | 1312 | 24 | blocked: `O-B0045-001` history getData HTTP 404 |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | `2026-07-03T16:20:00+08:00` | 1313 | 33 | blocked: `O-B0045-001` history getData HTTP 404 |

## Full Collection Status

All three windows have complete local 10-minute CWA collections under ignored `data/external/`
paths. Collection manifests, summaries, tensor archives, and run summaries stay under ignored
`data/processed/` paths.

| Event ID | Frames | Sliding Windows | Tensor Shape |
| --- | ---: | ---: | --- |
| `cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening` | 49 | 38 | `38 x 6 x 881 x 921 x 1` input, `38 x 6 x 881 x 921 x 1` target |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon` | 37 | 26 | `26 x 6 x 881 x 921 x 1` input, `26 x 6 x 881 x 921 x 1` target |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | 37 | 26 | `26 x 6 x 881 x 921 x 1` input, `26 x 6 x 881 x 921 x 1` target |

Use the same command shape to reproduce a collection:

```bash
minxiong-hydrocast-cwa-event-plan \
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

After each full collection, rerun `minxiong-hydrocast-radar-event-summary` with the default
`--expected-cadence-minutes 10`.

## Tensor And Metrics Commands

Convert a full collection into 6-frame input and 6-frame target sliding windows:

```bash
minxiong-hydrocast-radar-tensor-convert \
  --source-format cwa_opendata_grid \
  --input data/processed/cwa_event_collection_taiwan_widespread_20260628_afternoon_evening.json \
  --event-id cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening \
  --input-length 6 \
  --prediction-length 6 \
  --cadence-minutes 10 \
  --window-stride-frames 1 \
  --output data/processed/cwa_tensor_taiwan_widespread_20260628_6in_6out.npz
```

Run persistence lead-time metrics:

```bash
minxiong-hydrocast-tensor-baseline-evaluate \
  --archive data/processed/cwa_tensor_taiwan_widespread_20260628_6in_6out.npz \
  --event-threshold-mm 35 \
  --output data/processed/cwa_persistence_taiwan_widespread_20260628_6in_6out.json
```

Validate QPE against rain gauges after local `O-B0045-001` and `O-A0002-001` captures are
available for the same event window. Use the direct history downloader for gauge captures:

```bash
minxiong-hydrocast-cwa-history-data-download \
  --data-id O-A0002-001 \
  --data-time 2026-07-02T15:30:00+08:00 \
  --output data/external/gauges/events/O-A0002-001_20260702153000.xml \
  --insecure-tls
```

Then run validation once the matching QPE grid exists:

```bash
minxiong-hydrocast-qpe-gauge-validate \
  --qpe-grid data/external/radar/events/<event>/O-B0045-001.json \
  --gauge-json data/external/gauges/events/<event>/O-A0002-001.json \
  --event-id <event_id> \
  --output data/processed/qpe_gauge_validation_<event_id>.json
```

Train the current Tiny U-Net/RainNet-style baseline on the Taiwan-wide event:

```bash
PYTHONPATH=src conda run -n VLM python -m minxionghydrocast.pipelines.torch_baseline_training \
  --archive data/processed/cwa_tensor_taiwan_widespread_20260628_6in_6out.npz \
  --output-dir data/external/checkpoints/tiny_unet_cwa_taiwan_widespread_20260628_6in_6out \
  --device cuda \
  --multi-gpu \
  --hidden-channels 8 \
  --batch-size 2 \
  --epochs 1
```

The later formal weighted experiment and independent validation workflow supersede this command;
see [model_strategy.md](model_strategy.md).

Evaluate with mini-batch inference:

```bash
PYTHONPATH=src conda run -n VLM python -m minxionghydrocast.pipelines.torch_baseline_evaluation \
  --archive data/processed/cwa_tensor_chiayi_minxiong_heavyrain_20260702_6in_6out.npz \
  --checkpoint data/external/checkpoints/tiny_unet_cwa_taiwan_widespread_20260628_6in_6out/tiny_unet_nowcaster.pt \
  --event-threshold 35 \
  --device cuda \
  --batch-size 1 \
  --output data/processed/tiny_unet_comparison_chiayi_minxiong_heavyrain_20260702_6in_6out.json
```

## Baseline Snapshot

At `35 dBZ`, the 1-epoch Tiny U-Net lowers aggregate RMSE but under-detects threshold events
compared with persistence. Treat it as a diagnostic baseline, not a deployable model.

| Event | Persistence RMSE | Persistence CSI | Tiny U-Net RMSE | Tiny U-Net CSI | Weighted Tiny U-Net RMSE | Weighted Tiny U-Net CSI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Taiwan-wide train | `8.311872` | `0.214701` | `8.100073` | `0.048339` | `6.820217` | `0.210941` |
| Chiayi/Minxiong 2026-07-02 test | `11.465393` | `0.278248` | `9.914263` | `0.086701` | `9.564780` | `0.246535` |
| Chiayi/Minxiong 2026-07-03 test | `10.421478` | `0.315475` | `9.496191` | `0.121837` | `8.719508` | `0.286868` |
