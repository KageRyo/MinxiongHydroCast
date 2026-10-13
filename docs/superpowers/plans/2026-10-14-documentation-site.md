# Documentation Site Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Publish a readable documentation site and project homepage through a verified GitHub PR.

**Architecture:** MkDocs reuses the existing Markdown with a custom homepage template and CSS.
Strict builds and generated-link checks protect the public site; GitHub Actions publishes main.

**Tech Stack:** Python, MkDocs 1.6.1, Jinja, CSS, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-10-14-documentation-site-design.md`

## Global Constraints

- Preserve English technical documentation and the localhost operational boundary.
- No live API calls, credentials, official raw data, analytics, or external fonts.
- Use Conventional Commits; no Co-authored-by trailers.
- Exclude theme sources and internal planning documents from published output.
- PR checks pass before authorized merge.

## Review Focus

- Project subpath: internal links and assets must resolve under `/MinxiongHydroCast/`.
- Empty and stale data: documentation must distinguish source outcomes and readiness.
- Historical evidence: dated numbers must never imply current runtime health.
- Mobile and keyboard navigation: homepage, search, and table content remain usable.
- Publication scope: Pages includes only public source documents and local assets.

### Task 1: Documentation and static-site foundation

**Files:** `mkdocs.yml`, `requirements-docs.txt`, `.gitignore`, `docs/index.md`,
`docs/documentation.md`, `docs/getting_started.md`, `docs/api_reference.md`,
`docs/contributing.md`, `docs/site_development.md`, `README.md`, `docs/completion_plan.md`.

**Interfaces:** Markdown documentation feeds MkDocs; homepage metadata selects `home.html`.

- [ ] Configure MkDocs navigation, search, strict link validation, and source exclusions.
- [ ] Add reading paths and runnable API examples; correct historical/current-state wording.
- [ ] Build with `python -m mkdocs build --strict`; expect exit 0.

### Task 2: Custom homepage and public-output validation

**Files:** `docs/theme/home.html`, `docs/assets/site.css`, `docs/assets/minxiong-outline.svg`,
`scripts/validate_site.py`, `tests/test_site_validation.py`.

**Interfaces:** `validate_site(site_dir: Path) -> list[str]` reports broken local href/src targets.

- [ ] Write tests for valid subpath links, missing files/anchors, escaped paths, and ignored external URLs.
- [ ] Run focused tests; expect failure before validator implementation.
- [ ] Implement validator and homepage using Jinja URL filters for project-subpath correctness.
- [ ] Run validator tests, strict build, generated-link check, and desktop/mobile browser checks.

### Task 3: CI, review, and GitHub flow

**Files:** `.github/workflows/docs.yml` and contributor site instructions.

**Interfaces:** PR job builds/validates public output; main-only deployment publishes the artifact.

- [ ] Add build and Pages deploy jobs with scoped permissions and deployment concurrency.
- [ ] Run lint, compile, public contracts, full tests, and strict docs build.
- [ ] Commit with Conventional Commits, request independent branch review, fix material findings.
- [ ] Push feature branch, open PR, inspect all checks, squash merge with explicit clean message.
- [ ] Confirm main checks and Pages deployment and report PR/site URLs.
