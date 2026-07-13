# Event Splits

MinxiongHydroCast splits radar data by weather event, never by random frames or sliding windows.
Random splits leak storm structure across train, validation, and test sets and overstate
nowcasting performance.

## Formal Manifest

The formal manifest is `data/samples/event_split_manifest.json`. Schema version `2.0` contains
only real CWA `O-A0059-001` sequences:

| Event ID | Split | Region | Window |
| --- | --- | --- | --- |
| `cwa_o_a0059_taiwan_candidate_20260707_morning` | train | Taiwan | `2026-07-07T04:00:00+08:00` to `2026-07-07T12:00:00+08:00` |
| `cwa_o_a0059_taiwan_widespread_20260710_daytime` | train | Taiwan | `2026-07-10T10:00:00+08:00` to `2026-07-10T20:00:00+08:00` |
| `cwa_o_a0059_taiwan_widespread_20260709_evening` | validation | Taiwan | `2026-07-09T16:00:00+08:00` to `2026-07-09T22:00:00+08:00` |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260703_afternoon` | test | Minxiong, Chiayi County | `2026-07-03T13:00:00+08:00` to `2026-07-03T19:00:00+08:00` |
| `cwa_o_a0059_chiayi_minxiong_heavyrain_20260711_early_morning` | test | Minxiong, Chiayi County | `2026-07-11T00:00:00+08:00` to `2026-07-11T06:00:00+08:00` |

The Pydantic manifest gate requires exactly `train`, `validation`, and `test`; minimum counts of
2/1/2; two Minxiong test events; unique IDs; complete split assignment; ordered timestamps; and
no `demo` source or ID. Candidate weather types remain radar-derived until official CWA weather
context is attached.

A newly discovered event must retain its `evidence_candidate_id`. Before it can enter this
manifest, `mhc event-review` must record a complete, synchronized, official-context-backed approval.
`event-split-check` and `dataset-build` accept `--event-evidence-catalog <path>` and share one gate
that verifies the approval, all cataloged checksums, the source data ID, exact window, and reviewed
regime. The build runs it before downloading data or training. Discovery and review commands never
choose or edit the formal split themselves.

## Independence Rules

- Training normalization is computed only from the combined training archive.
- The validation event is a separate archive used for model selection and early stopping only.
- Validation samples never contribute to gradients.
- Both Minxiong/Chiayi events remain untouched until final model comparison.
- Promotion requires the learned model to beat Persistence on aggregate and lead-time gates; a
  lower RMSE alone is insufficient.

The current weighted Tiny U-Net fails that promotion gate, so forecast publication remains
disabled. See [research_dataset.md](research_dataset.md) for the build, metrics, catalog, and
verification evidence.

## Commands

Validate the general event-split contract:

```bash
mhc event-split-check \
  --manifest data/samples/event_split_manifest.json \
  --event-evidence-catalog "$MINXIONGHYDROCAST_RESEARCH_ROOT/discovery/event_evidence_catalog.json" \
  --output data/processed/event_split_check.json \
  --require-ok
```

Build and validate the stronger formal dataset contract:

```bash
mhc dataset-build \
  --manifest data/samples/event_split_manifest.json \
  --event-evidence-catalog "$MINXIONGHYDROCAST_RESEARCH_ROOT/discovery/event_evidence_catalog.json" \
  --root "$MINXIONGHYDROCAST_RESEARCH_ROOT"
```

The evidence-catalog argument is required for either command only after the manifest references a
discovery candidate.

Historical candidate evidence may remain in `data/samples/radar_event_windows.json` and
`data/samples/event_expansion_queue.json`, but it does not belong to an active split until the
formal manifest includes it and the complete build succeeds.
