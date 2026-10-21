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
- [x] Write failing gap/corruption/duplicate/drift/day-boundary/budget/root-escape/source-attempt tests.
- [x] Implement strict inventory, adapters for dataset/discovery catalogs, native grid verification,
  deterministic slot/day/event counts, intervals and safe provenance/failure categories.
- [x] Verify focused and full tests, commit.

## Task 2: CLI/local view and release preparation

Files: pipelines/archive_coverage.py, research/coverage_view.py, cli.py, scripts/package_smoke.py,
tests/test_archive_coverage.py, docs/archive_coverage.md, docs/releases/v0.1.8.md, README,
CHANGELOG, CITATION, pyproject, __init__, navigation/roadmap/tasks/research docs.
- [x] Add failing CLI/demo/export cases; implement JSON/table/semantic offline HTML with safe,
  exclusive output and synthetic native frame fixtures.
- [x] Browser-check local view/keyboard/mobile/offline; bounded real dataset/discovery cases.
- [x] Update v0.1.8 metadata/docs and installed-package smoke workflows.
- [x] Run full/lint/types/docs/wheel checks; one fresh final review and regression fixes.
- [ ] Verify committed protocol reconstruction and CI.
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

- Core and view delivery: 25 coverage integration cases and 470 full tests pass; Ruff and targeted
  Pyright pass, strict docs/link checks pass. Installed v0.1.8 wheel demos and localhost service
  smoke pass when its bin directory is explicitly selected in PATH.
- Final review fixes: conflicting catalog pins -> metadata failure; contained symlink retains
  recorded pin; duplicate missing records also count as missing. Three regressions RED→GREEN.
- Real preserved probes: dataset 110 expected/present slots, 12 structurally usable checks and
  98 unchecked; discovery 134 expected/present, 12 usable and 122 unchecked. Two entries per
  catalog; remaining entries explicitly omitted. Catalog/formal-manifest hashes unchanged.
- Legacy dataset input preparation: exact recorded public manifest hash/bytes verified before
  copying to its referenced external relative path. Reporter still reads only inside the root.
