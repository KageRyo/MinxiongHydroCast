# Offline event replay

`mhc event replay` exports a self-contained HTML snapshot of preserved radar observations,
verified baseline forecasts and saved scores. Open the file directly in a browser. No server,
credentials, tiles, external fonts or network connection are needed. This command is in the
current development source; published software v0.1.7 predates it.

## Try the synthetic event

Install the development source and generate a new destination:

```bash
python -m pip install -e .
mhc event replay --demo --output /tmp/hydrocast-replay.html
```

Open `/tmp/hydrocast-replay.html`. The demo produces moving-cell radar frames, processes them
through the real Persistence/Optical Flow backtest engine, then verifies and exports its saved
artifacts. A second event has no saved forecasts, and a missing radar interval demonstrates
pending targets. Synthetic hourly QPE and WGS84 gauges remain separate from TWD67 radar.
Temporary raw files and backtest records are removed after export. No official data is bundled.

## Replay your preserved archive

First generate a [rolling backtest](rolling_backtests.md). Then export its report:

```bash
mhc event replay \
  --root /external/hydrocast-data \
  --report backtests/latest.json \
  --output /external/hydrocast-data/exports/event-replay.html
```

Report and context paths are relative to `--root`; absolute paths are accepted only within that
root. All resolved source, snapshot, forecast and score paths must remain there, including
symlinks. Output must be a **new** `.html` file below the data or system temporary root, outside
project source. Existing files are never overwritten. Choose a new destination for each export.
The exporter reads artifacts without changing them or regenerating predictions/scores.

The HTML embeds sampled observations and predictions. It omits private host paths and URLs,
but still contains research data: keep it private unless you have permission to share it.
Checksum verification detects drift; it does not authenticate historic acquisition.

## Inspect the event

- Select an event, model and forecast lead. The time slider selects an observation/forecast origin.
  Previous/Next and Play/Pause move through the stored observation times; gaps are not filled in.
- For a saved forecast, the three panels show the target observation at the selected lead,
  the saved prediction, and signed forecast-minus-observation error. At times with no forecast,
  only the selected observation is shown. Missing/corrupt artifacts have explicit states.
- Scores are verified against the saved per-lead records. Both models use the same common mask;
  the displayed full-resolution RMSE/MAE/CSI/POD/FAR are never recalculated from previews.
- Timestamps are shown in UTC. Observation time, report cutoff/production and forecast production
  are separate. Radar acquisition time is `unknown` because the backtest manifest does not record it.
- Native row/column previews use nearest sampling without reprojection or interpolation. The
  source grid, datum, spacing, origin and sampling stride are visible. Native row zero is at the
  top; this is an array comparison, not a geographic basemap. Transparent pixels are unavailable.
  dBZ colors clip to 0–60, signed errors to ±30 and QPE to 0–50 mm; scores remain unchanged.

Controls have visible focus, explicit labels and keyboard operation. Playback starts only on
request, pauses when changing controls or leaving the tab, and stops with Escape.

Default export limits are 120 observation frames, 24 forecast origins and 160 pixels along the
longest preview axis. `--max-frames`, `--max-windows` and `--preview-size` allow bounded changes.
The frame budget also bounds forecast input/target reads; targets outside it remain omitted.
A combined 24-million preview-cell budget rejects overly large option combinations. At most
24 context artifacts and 200 gauge stations per artifact are included. Omitted context/station
counts are visible. Omitted frame/origin counts are visible in the HTML; the snapshot is not an archive-coverage
assessment. Events with no included frames retain an explicit empty state.

## Optional hourly QPE and gauge context

Supply an external context manifest with source hashes/byte counts recorded at collection time:

```json
{
  "schema_version": "1.0",
  "artifacts": [{
    "event_id": "research_event_one",
    "kind": "qpe",
    "path": "raw/qpe/hour.json",
    "data_time": "2026-07-01T00:20:00+00:00",
    "fetched_at": "2026-07-01T00:22:00+00:00",
    "interval_minutes": 60,
    "bytes": 12345,
    "sha256": "<64 lowercase hexadecimal characters>"
  }]
}
```

Use `--context replay_context.json`. `fetched_at` may be omitted; all supplied times must have
an explicit timezone. Artifact keys `(event_id, kind, data_time)` must be unique. For gauges,
use `kind: "gauges"` and a preserved official hourly station JSON/XML payload. Only explicitly
hourly rainfall keys are accepted; ambiguous generic rainfall fields are not interpreted.

QPE must be valid `O-B0045-001` in mm with a known declared geographic datum. Gauge data is
identified as `O-A0002-001` hourly mm; station end times must match the context record. The initial
adapter accepts **60-minute** intervals only. Unknown datums, timestamp mismatches or invalid source
contracts produce an invalid state; missing files produce a missing state. Separate QPE previews
and gauge tables retain their own datum and end time. Different known datums are never overlaid,
matched or compared numerically, and hourly rainfall is never treated as instantaneous dBZ.

No human weather/flood annotations, formal split changes or operational publication gates are
part of this viewer. Archive coverage remains [#60](https://github.com/KageRyo/MinxiongHydroCast/issues/60).
