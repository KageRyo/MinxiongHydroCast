# Event Splits

FloodCastTW should split model data by weather event, not by random rows or radar frames. Random
splits leak storm structure across train, validation, and test sets, which makes nowcasting scores
look better than they are.

## Manifest

The sample manifest is `data/samples/event_split_manifest.json`. It contains demo-safe placeholder
events, one live-verified CWA `O-A0059-001` radar sequence sample for pipeline smoke tests, and
radar-derived candidate windows selected from a CWA hourly discovery scan:

- `split_strategy`: must be `event_based`
- `target`: model or task family
- `events`: event ID, type, region, start/end time, source, and notes
- `splits`: event IDs assigned to `train`, `validation`, and `test`

The current tracked radar candidates are:

| Event ID | Split | Region | Window | Basis |
| --- | --- | --- | --- | --- |
| `cwa_o_a0059_taiwan_widespread_20260628_afternoon_evening` | train | Taiwan | `2026-06-28T13:00:00+08:00` to `2026-06-28T21:00:00+08:00` | largest Taiwan-wide 35 dBZ coverage in full sequence |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260702_afternoon` | test | Minxiong, Chiayi | `2026-07-02T12:00:00+08:00` to `2026-07-02T18:00:00+08:00` | highest local-focus dBZ in hourly scan |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | test | Minxiong, Chiayi | `2026-07-03T13:00:00+08:00` to `2026-07-03T19:00:00+08:00` | largest local-focus 35 dBZ coverage in hourly scan |

Candidate evidence is tracked in `data/samples/radar_event_windows.json`. These labels are
radar-derived only; attach official CWA weather context before calling a window typhoon or frontal.
Replace the remaining demo events before training or reporting scientific results. The 3-frame CWA
sample verifies the pipeline only; it is not a benchmark event.

## Check Command

```bash
floodcasttw-event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --output data/processed/event_split_check.json
```

Use `--require-ok` in training automation:

```bash
floodcasttw-event-split-check --require-ok
```

The checker verifies:

- required split names exist and are non-empty
- event IDs are unique
- an event does not appear in more than one split
- split references point to known events
- event start/end times are valid and ordered
- the strategy is explicitly event-based

## Local Model Guidance

For a Minxiong-specific model, keep at least one Minxiong or Chiayi flood-producing event entirely
out of training. Train on broader Taiwan/Chiayi events, then evaluate the local event split
separately. A tiny Minxiong-only training set is likely to overfit.
