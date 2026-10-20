# Archive coverage and research workflow release

Complete issue #60 and publish software v0.1.8 with rolling backtests, offline replay and archive
coverage. No human annotations, network retries, source substitution or readiness changes.

## Contract

`mhc data archive-coverage --root ROOT --catalog CATALOG --format json|table|html` reads existing
dataset/discovery catalogs. Also accept an explicit strict inventory for other native radar/QPE
archives: event/product, aware inclusive start/end, cadence, units/datum, timestamped pinned file
references and optional typed source attempts. Convert existing source schemas without editing them.
Discovery candidates use the configured cadence and verified collection artifact for timestamps;
dataset catalogs use their verified source manifest/config and collection. Corrupt/missing
collection metadata produces an unknown/unverified event state, not invented missing captures.

For each scheduled timestamp retain distinct presence, size, SHA-256 and usability flags. Aggregate
slot counts by event/product and local day (default Asia/Taipei). Duplicate timestamps cannot be
usable. Extra/off-cadence/outside-window records are disclosed separately and never inflate coverage.
Native CWA O-A0059-001 dBZ and O-B0045-001 mm are supported; require matching header time, product,
units, known declared datum, positive/finite grid geometry, stable native-grid signature and at least
one valid finite pixel. These checks establish structural radar/QPE usability, not hydrological
validity, model skill or flood-risk calibration. Catalog-only existence is not capture verification.

Missing intervals distinguish uncaptured/missing files from unknown metadata and unchecked work.
Failures remain explicit: duplicate, escaped path, byte/hash mismatch, malformed source, wrong time,
product/unit/datum/grid drift, all nodata and verification budget exhausted. Do not redefine a
recorded hash or ignore a failed frame to make the archive appear complete.

Reports are deterministic for identical inputs/files/options. Record catalog SHA and pinned metadata
checks; export safe IDs/times/counts/checksums and fixed reason codes. Never include host paths,
URLs, error strings or keys. Source attempts separate 404, auth, rate limit, transport, HTTP-other
and unknown. Trace them by event/product/target/attempt time and input record index/hash; a tested
404 result never implies a documented retention policy. No retry plan or retry executor is added.
Existing ingestion remains the separate explicit acquisition interface.

Bound expensive verification by default 250 artifact checks and 10 event/product entries; report
omitted entries and unchecked slots. Hard limits 10,000 checks and 100 entries, 100,000 scheduled
slots per inventory. Every read and resolved symlink stays in the external data root. Outputs are
new files below external root or system temp, outside project source; no overwrite. An exporter
may create its requested output, but never mutates source files/catalogs/splits.

## Local view

Use the operator/replay slate/white palette and system sans-serif. A standalone HTML shows the
coverage funnel as labeled counts, event/day/product tables, missing intervals, per-slot checks
and source-attempt classifications in expandable native details. Text accompanies color. No
external assets or JavaScript; a hash-restricted stylesheet and semantic tables work offline and
with keyboard/mobile. A credential-free synthetic demo includes gaps, checksum drift, duplicate
times, structural quality failures and typed 404/auth/rate-limit/transport attempts.

## Release

Update pyproject, package __version__, CITATION, CHANGELOG, README/roadmap/tasks and source-only
research command docs to v0.1.8. Add release notes and installed-package smoke exercises for both
new offline commands. Preserve the independently published dataset-protocol-v0.2.0 artifact/version.
Require tests, lint/types, docs, browser/offline check, bounded real archive report, built-wheel
smoke and protocol reconstruction, fresh final review and CI before merge. Then create the GitHub
v0.1.8 release, verify release automation/PyPI files and an installed published-wheel demo.
