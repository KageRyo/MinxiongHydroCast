# Changelog

All notable changes to MinxiongHydroCast are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `mhc event replay`: export a standalone offline radar/forecast/error viewer with verified saved
  scores, playback, optional segregated hourly QPE/gauge context and a credential-free synthetic demo.

- `mhc model rolling-backtest`: persist input-only Persistence/Optical Flow forecasts and score
  arriving radar observations per origin/lead, with immutable checksummed records, bounded new
  work, shared validity masks, source/code provenance and opt-in scheduling templates.

### Planned

- An archive coverage dashboard built on the research artifact
  contracts; no manual weather/flood annotations required.
- Independent model, lead-time, label, and shadow-gate completion for `v0.3.0`.

## [0.1.7] - 2026-10-20

### Added

- Deterministic protocol-source archive build and verification commands with committed source
  provenance, a pinned event manifest, synthetic fixtures, and per-file checksums.
- CI reconstruction from the extracted archive and a separate verified GitHub release asset.
- Public documentation site, dated operational evidence, and a dataset-milestone acceptance record.
- Checksum-pinned formal frame/source/build-provenance inventories and a label-free protocol
  policy, with independent `dataset-protocol-v0.2.0` release notes and citation.

### Fixed

- Public manifest drift checks and normalized QPE/gauge evidence validation.
- Require equal timezone-aware observation times and a common declared geographic datum for
  QPE/gauge matching; select native station coordinate pairs together and reject production-time
  substitutions, unknown datums and unsupported QPE products/units.
- Event discovery catalog integrity performance and kernel-backed locking across PID namespaces.

### Publication boundary

- This software patch ships verification tooling and the label-free protocol policy. The
  independently published protocol does not require manual labels. Raw observations, tensors,
  checkpoints and private catalogs remain external; legacy acquisition/QPE limits and existing
  model/notification gates remain explicit.

## [0.1.6] - 2026-08-18

### Removed

- The retired `AIWeatherForecast` legacy boundary document and its documentation-index link. The
  host-side legacy directory was already removed after a retained independent archive was confirmed.

### Documentation

- Keep the v0.1.4 changelog entry as released historical evidence; it is no longer an active
  migration or retention instruction.

## [0.1.5] - 2026-08-18

### Added

- `mhc data relocate-root`, a no-write-first command that updates the external data-root binding
  after data files are moved or copied.
- Atomic backups and rollback of changed collection and catalog JSON, with a refreshed dataset
  verification report for a changed dataset catalog.

### Safety

- The relocation preflight rejects missing artifacts, unexpected roots, root escapes, and checksum
  mismatches not caused by rewritten collection manifests. It never moves or deletes data payloads.

## [0.1.4] - 2026-08-18

### Added

- A preferred `MINXIONGHYDROCAST_DATA_ROOT` setting and `--data-root` event-discovery option,
  while accepting the former research-root setting during migration.
- Verified private deployment metadata recording the installed package version, source revision,
  installation time, and Python version.
- Explicit storage, Git-policy, and legacy-AIWeatherForecast boundary documentation.

### Changed

- Rename the external artifact layout and documentation from research to data and model assets.
- Write `data_root` in new dataset and event-evidence catalogs while accepting existing
  `research_root` catalogs.

### Safety

- Runtime state, raw official captures, evidence, model artifacts, and backups remain external to
  the Git checkout; ignored in-checkout paths are a safety net only.

## [0.1.3] - 2026-08-18

### Changed

- Align the package metadata, runtime `__version__`, citation metadata, issue-template example,
  and release documentation at `0.1.3`.

### Safety

- This is a metadata-only patch release; the v0.1.2 research and forecast-publication boundaries
  remain unchanged.

## [0.1.2] - 2026-08-17

### Added

- Deterministic CPU optical-flow rainfall nowcasting with FFT phase correlation and global
  integer translation.
- Per-event and per-lead-time RMSE, MAE, CSI, POD, and FAR comparisons against Persistence.
- Split-safe public aggregate reporting for Persistence, Optical Flow, and Tiny U-Net without
  private archive or checkpoint paths.

### Changed

- Dataset builds now persist checksummed optical-flow evaluation artifacts in the external
  research root.
- The release workflow verifies that GitHub Release display names use the
  `MinxiongHydroCast vX.Y.Z` convention.

### Safety

- Optical Flow remains a research benchmark; the independent aggregate does not beat Persistence
  and the forecast promotion gate remains unchanged.

## [0.1.1] - 2026-08-01

### Added

- Credential-free Docker Compose demo with deterministic synthetic observations, a read-only
  dashboard, health/readiness endpoints, metrics, and a fail-closed forecast gate.
- Strict, packaged region profiles for Minxiong and an example region, with a documented adapter
  contract and contract validation helpers.
- Contributor guide, structured issue forms, pull-request template, clean-wheel smoke test, and
  OIDC-based PyPI release workflow.
- Read-only shadow gap incident reporting with source, attempt, snapshot, recovery, and pending
  human-review evidence.

### Changed

- Reduced the base installation to NumPy, Pydantic, and Requests; scraping, reporting, modeling,
  and development dependencies now use capability extras.
- Consolidated installed command-line entry points under the single grouped `mhc` executable while
  retaining transition aliases for legacy command tokens.
- Generalized the Minxiong-only derived feature dataset to profile-driven `region_features` while
  retaining the legacy read-only API route.

### Safety

- Synthetic demo data remains explicitly classified as `demo_fixture` and cannot satisfy
  operational readiness or forecast publication.
- Region-profile boundaries are labeled according to their authority and must not be inferred as
  official administrative geometry.

## [0.1.0] - 2026-07-29

### Added

- Official CWA rain-gauge, WRA rainfall-warning, and WRA IoW flood-sensor ingestion.
- Strict schemas, freshness checks, immutable snapshots, provenance, and SHA-256 integrity.
- CLI, read-only API, health/readiness endpoints, Prometheus metrics, and operator dashboard.
- Localhost-only systemd profile, alert auditing, verified backup/restore, and shadow evaluation.
- CWA radar/QPE discovery, bounded event evidence, human review, and fixed split validation.
- Persistence and Tiny U-Net training/evaluation with independent event and lead-time metrics.
- Dependabot, scheduled official-source contract checks, Python 3.11/3.13 CI, and CodeQL.

### Changed

- Added bounded retries for empty, invalid, malformed, or repeated WRA pages.
- Added bounded full measurement/catalog transaction retries when source data changes mid-join.
- Published structured per-source retry telemetry in run summaries, manifests, API status, and
  Prometheus metrics.
- Reorganized the README around architecture, evidence, limits, and a concise Quick Start.
- Replaced host-specific deployment details with public-safe, parameterized documentation.

### Safety

- Scraper fallback remains degraded and cannot satisfy readiness.
- Schema drift and broken WRA joins remain fail-closed.
- Radar candidates cannot automatically enter formal train/validation/test splits.
- Forecast publication and automated notification remain disabled until all gates pass.

[Unreleased]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/KageRyo/MinxiongHydroCast/releases/tag/v0.1.0
