# Task List

This list replaces GitHub issues for now. Keep tasks small enough to finish, test, and push on
`main`.

## Active

- [x] Add CI for compile, lint, and tests.
- [x] Add NowcastNet adapter smoke test and external asset manifest.
- [x] Emit structured run summaries for every command-line pipeline.
- [x] Add radar source manifest checks before tensor conversion.
- [x] Define train/validation/test split rules by weather event.
- [x] Add a tiny tracked radar-like fixture for model contract tests.
- [x] Add a dry-run radar tensor conversion skeleton.
- [x] Add a radar source adapter interface for tensor conversion.
- [x] Verify the persistence baseline accepts converted tensor fixtures.
- [x] Add a tensor archive baseline evaluation command.
- [x] Identify official CWA radar/QPE candidate data IDs and license URL.
- [x] Implement a CWA file API downloader that reads `CWA_API_KEY` from local environment only.
- [x] Download CWA `O-A0059-001` and `O-B0045-001` sample files with a local API key.
- [x] Confirm CWA radar/QPE CRS, grid origin, shape, nodata encoding, timestamps, and units.
- [x] Add schema inspection tests for CWA `O-A0059-001` and `O-B0045-001` sample captures.
- [ ] Populate event split manifest with confirmed historical radar events.

## Next

- [ ] Confirm CWA historyAPI retention and file list workflow for `O-A0059-001`.
- [ ] Build a multi-frame CWA radar event collector under ignored `data/external/`.
- [ ] Build a production radar tensor converter once the source format is confirmed.
- [ ] Add a production radar source adapter once native format is confirmed.
- [ ] Wire NowcastNet inference only after code, checkpoint, and license are reviewed.
- [ ] Use one RTX 4090 for the first training run; move to two GPUs after data loading,
      checkpointing, and recovery are repeatable.

## Later

- [ ] Add scheduled jobs after live ingestion is stable for repeated manual runs.
- [ ] Add alerting only after run summaries expose reliable failure reasons.
- [ ] Publish model cards for any Taiwan or Minxiong-specific checkpoints.
