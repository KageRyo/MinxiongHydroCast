# Event Splits

FloodCastTW should split model data by weather event, not by random rows or radar frames. Random
splits leak storm structure across train, validation, and test sets, which makes nowcasting scores
look better than they are.

## Manifest

The sample manifest is `data/samples/event_split_manifest.json`. It contains demo-safe placeholder
events, plus one live-verified CWA `O-A0059-001` radar sequence sample for pipeline smoke tests:

- `split_strategy`: must be `event_based`
- `target`: model or task family
- `events`: event ID, type, region, start/end time, source, and notes
- `splits`: event IDs assigned to `train`, `validation`, and `test`

Replace the remaining demo events with confirmed historical heavy-rain, typhoon, and frontal events
before training or reporting results. The current CWA sample verifies the pipeline only; it is not a
benchmark event.

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
