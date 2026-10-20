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
- [ ] Add failing CLI/export tests, implement atomic non-overwriting safe output and demo.
- [ ] Build three-panel native radar comparison, event/time/model/lead selectors, playback,
  metrics/context/provenance, clear missing states and responsive keyboard-accessible controls.
- [ ] Browser-check controls, mobile, offline behavior and screenshot; bounded real archive run.
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
