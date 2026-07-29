# Changelog

All notable changes to MinxiongHydroCast are documented here. The project follows
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Planned

- Broader human-reviewed radar-event diversity and QPE/gauge validation for `v0.2.0`.
- Independent model, lead-time, label, and shadow-gate completion for `v0.3.0`.

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

[Unreleased]: https://github.com/KageRyo/MinxiongHydroCast/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/KageRyo/MinxiongHydroCast/releases/tag/v0.1.0
