# Offline event replay implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation.

**Goal:** Deliver issue #59 as a verified standalone offline research viewer.
**Spec:** docs/superpowers/specs/2026-10-20-event-replay.md
**Base:** 83da4b0943cd5f1c7c096891d06bb35d8e55aad7

## Task 1: verified replay payload

Files: research/replay.py, research/replay_context.py, tests/test_event_replay.py.
- [x] Write integration tests using real synthetic backtest artifacts; watch expected failures.
- [x] Implement bounded root-safe read-only replay data, common-mask signed preview errors,
  saved score verification and whitelisted provenance. Add segregated optional QPE/gauge context.
- [x] Verify missing/corrupt/escaped/unaligned states and no mutations; run full suite, commit.

## Task 2: offline interface and CLI

Files: research/replay.html, research/replay_demo.py, pipelines/event_replay.py, cli.py,
pyproject.toml, tests/test_cli.py, docs/event_replay.md, README, CHANGELOG, mkdocs.yml.
- [x] Add failing CLI/export tests, implement atomic non-overwriting safe output and demo.
- [x] Build three-panel native radar comparison, event/time/model/lead selectors, playback,
  metrics/context/provenance, clear missing states and responsive keyboard-accessible controls.
- [x] Browser-check controls, mobile, offline behavior and screenshot; bounded real archive run.
- [ ] Update source-only documentation; lint/types/full suite/docs/package/protocol checks.
- [ ] Final fresh read-only review, fix important findings with regression tests, create PR and CI.

## Ledger

- User requests continuing the assessed backlog. Execute inline in the existing isolated linked
  worktree, branch feat/offline-event-replay; no redundant authorization round.
- Static export selected over an API extension: keeps this delivery offline and portable with no
  second service to run. Acquisition times not present in backtest manifests remain unknown.
- Limits apply before source array reads; disclose truncated windows/frames rather than imply
  complete archive coverage. Archive coverage remains separate issue #60.

- Task 1: twelve integration cases RED (missing replay module) -> GREEN. QPE fixture declares
  TWD67經緯網格; preserve that known source datum instead of silently relabeling it.

- Final review: missing/corrupt scored targets must downgrade status; the frame budget must also
  exclude forecast input/target reads. Both findings plus malformed-window diagnostic are covered
  by failing regressions then fixes. Classified malformed-window handling as important because
  the CLI would otherwise emit a traceback for an invalid external report. Context and combined
  preview budgets and a 16-frame source cache bound the remaining export memory.

- Task 2 and review fix pass: 27 focused cases and 444 full tests passed, Ruff and targeted
  Pyright passed (zero errors), strict documentation/link validation passed. Browser assertions
  covered model/lead/event selection, pending targets, play/Escape, keyboard slider, QPE/gauges,
  empty context, 375px mobile width and zero network resources with networking disabled.
- Bounded preserved export: 8 frames, 1 two-model forecast, 2 scored leads, 1,174,759-byte HTML,
  no private host paths. Desktop/mobile screenshots and raw HTML remain outside the repository.
- Final: fixed missing scored target, global frame-read budget, malformed report diagnostic,
  malformed XML and timestamp-type handling — regression cases RED→GREEN; suite 444/444.
