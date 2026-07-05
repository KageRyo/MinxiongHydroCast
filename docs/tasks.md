# Task List

This list replaces GitHub issues for now. Keep tasks small enough to finish, test, and push on
`main`.

## Active

- [x] Add CI for compile, lint, and tests.
- [x] Add NowcastNet adapter smoke test and external asset manifest.
- [x] Emit structured run summaries for every command-line pipeline.
- [x] Add radar source manifest checks before tensor conversion.
- [ ] Confirm source radar data format, cadence, projection, and licensing.
- [ ] Define train/validation/test split rules by weather event.

## Next

- [ ] Build a radar tensor conversion command once the source format is confirmed.
- [ ] Add a tiny tracked radar-like fixture for model contract tests.
- [ ] Run persistence baseline on the same tensor format used by SOTA models.
- [ ] Wire NowcastNet inference only after code, checkpoint, and license are reviewed.
- [ ] Use one RTX 4090 for the first training run; move to two GPUs after data loading,
      checkpointing, and recovery are repeatable.

## Later

- [ ] Add scheduled jobs after live ingestion is stable for repeated manual runs.
- [ ] Add alerting only after run summaries expose reliable failure reasons.
- [ ] Publish model cards for any Taiwan or Minxiong-specific checkpoints.
