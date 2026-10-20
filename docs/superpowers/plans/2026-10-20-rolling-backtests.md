# Rolling radar backtests implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Generate immutable baseline forecasts and incrementally score arriving radar targets.
**Architecture:** Strict manifest/config contracts; native-grid frame validation; checksummed
forecast/score storage; one-shot runner using existing baseline predictors and metric helpers.
**Tech Stack:** Python3.11+, NumPy, Pydantic, existing atomic storage, fcntl; no new dependency.
**Spec:** docs/superpowers/specs/2026-10-20-rolling-backtests.md

## Global constraints

- Research only, external data root, no human labels, no formal split/promotion/readiness edits.
- Aware timestamps, exact cadence/grid/units, declared nodata and input-only prediction.
- Existing fixed benchmark remains unchanged; no training or normalization in this engine.

## Review focus

- Arriving targets must never regenerate cached forecasts or alter already committed scores.
- Same-size file/cache corruption, changed input identity and path escapes must fail closed.
- Missing cadence histories and all-nodata lead times must remain explicit exclusions.
- Identical masks and metric denominators must make baseline comparisons fair.
- Concurrent runs and interruption before/after commit must not duplicate or corrupt output.

## Task1: manifest, storage and frame contracts

Files: models/rolling_backtest.py, pipelines/backtest_store.py, tests/test_rolling_backtest.py.
- [x] Write failing schema/storage tests for aware times, duplicate IDs/times, root escapes,
  configuration changes and tamper detection.
- [x] Implement strict frame/event/config contracts, pinned record IO and a nonblocking kernel lock.
- [x] Verify focused tests; keep forecast commit semantics explicit.

## Task2: rolling generation and scoring

Files: pipelines/rolling_backtest.py and tests/test_rolling_backtest.py.
Interface: run_backtest(manifest_path, root, config, as_of=None, max_new_windows=24) -> dict.
- [x] Write failing tests for pending-to-scored updates, input-only forecasts, input changes,
  masks, incorrect units/grids, corruption, missing frames, bounded resume and all-nodata states.
- [x] Implement native-frame loading, immutable forecast arrays, per-lead common-mask scoring
  with existing predictors/metrics, cached-record reuse and atomic run summaries.
- [x] Verify exact synthetic metric counts and preserved forecast bytes across repeated runs.

## Task3: CLI, scheduling and evidence

Files: cli.py, tests/test_cli.py, docs/rolling_backtests.md, docs/tasks.md, docs/roadmap.md,
README.md, deploy/systemd-user/minxiong-hydrocast-backtest.{service,timer}.
- [x] Write a failing CLI integration test, wire command and add disabled scheduling templates.
- [x] Document manifest production, research-only scope, integrity and retry/limit semantics.
- [x] Run focused/full tests, lint/type checks and docs build; run a bounded preserved-source case.
- [ ] Request one read-only whole-branch review, fix important findings and create a verified PR.

## Execution ledger

- User explicitly requested starting the first approved feature; execute inline without another
  authorization round. Existing linked worktree provides isolation; branch feat/rolling-radar-backtests.
- Other two issues remain scoped future work; their user interfaces are not implemented here.

- Ruling: Keep the existing project-specific external-root guard. A proposed blanket ban on
  every ancestor containing .git was rejected: /tmp itself is a Git checkout in this harness,
  and unrelated private data/catalog repositories are not the project source boundary. The
  speculative guard and its overbroad test were removed; source/forecast/report path escape
  tests and the original project-root restriction remain intact.
- Core review P2 fixed with red/green tests for run/snapshot output symlinks. Snapshot checksum
  and package-relative code-identity keys also have red/green regression coverage.
- Verification: 39 focused tests, 414 full tests, Ruff, targeted Pyright and strict docs/link
  validation passed. Bounded preserved run: 8 frames, 1 immutable two-model forecast, 2 arriving
  targets, 0 new scores on repeat; original source catalog and formal split unchanged.
- Service/timer syntax checked with a temporary inert executable; no units installed/enabled.
- Remaining integration: final review results, committed-source reconstruction and CI/PR.
