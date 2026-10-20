# Archive coverage and v0.1.8 implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline implementation.

**Goal:** Complete #60 and publish all three research workflows as v0.1.8.
**Spec:** docs/superpowers/specs/2026-10-20-archive-coverage.md
**Base:** 6e2b0df4e214672e3ee87bf78207509d8ccd54c3

## Constraints / review focus

- Exact source identity and timestamps; expected/present/size/hash/usable are distinct slot counts.
- Duplicates/outside-cadence frames cannot inflate denominator or quality counts.
- Missing collection metadata is unknown availability, not confirmed missing raw frames.
- Limits must bound real artifact reads and disclose unchecked/omitted work.
- Safe diagnostics/export; no network or source mutations; no label/promotion/readiness changes.

## Task 1: report engine and catalog adapters

Files: models/archive_coverage.py, research/archive_inventory.py, research/archive_coverage.py,
tests/test_archive_coverage.py.
Interface: build_coverage(root, catalog_path, max_checks=250, max_entries=10, timezone='Asia/Taipei').
- [ ] Write failing gap/corruption/duplicate/drift/day-boundary/budget/root-escape/source-attempt tests.
- [ ] Implement strict inventory, adapters for dataset/discovery catalogs, native grid verification,
  deterministic slot/day/event counts, intervals and safe provenance/failure categories.
- [ ] Verify focused and full tests, commit.

## Task 2: CLI/local view and release preparation

Files: pipelines/archive_coverage.py, research/coverage_view.py, cli.py, scripts/package_smoke.py,
tests/test_archive_coverage.py, docs/archive_coverage.md, docs/releases/v0.1.8.md, README,
CHANGELOG, CITATION, pyproject, __init__, navigation/roadmap/tasks/research docs.
- [ ] Add failing CLI/demo/export cases; implement JSON/table/semantic offline HTML with safe,
  exclusive output and synthetic native frame fixtures.
- [ ] Browser-check local view/keyboard/mobile/offline; bounded real dataset/discovery cases.
- [ ] Update v0.1.8 metadata/docs and installed-package smoke workflows.
- [ ] Run full/lint/types/docs/wheel/protocol checks; one fresh final review and regression fixes.
- [ ] Create English labeled PR, pass CI, merge; check #60 closure.

## Task 3: publish and verify

- [ ] Create v0.1.8 GitHub release at the tested merged commit with reviewable release notes.
- [ ] Verify build, source attachments and PyPI publish workflow; download checksum-verified PyPI
  artifacts and smoke-test the actual published wheel in a separate environment.

## Ledger

- User explicitly authorizes completing #60 and publishing a new version. Use existing isolated
  worktree on feat/archive-coverage-release; no repeated authorization round.
- v0.1.8 continues the established software release line. Independent dataset-protocol-v0.2.0
  and future operational/model milestones remain separate.
