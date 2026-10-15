# Dataset milestone acceptance

This record tracks [issue #31](https://github.com/KageRyo/MinxiongHydroCast/issues/31).
Verification dated 2026-10-15 covers the source contracts and synthetic reconstruction path;
it does not certify a released official dataset or forecast readiness.

| Acceptance criterion | Evidence | Remaining work |
| --- | --- | --- |
| Clean checkout validates the manifest and rebuilds synthetic tensors | Fresh Python 3.13 environment; public-contract validation and 90 relevant tests passed, including synthetic CWA grids, sliding tensors, and NPZ round trips | Keep reproducible commands and verification outputs with the release artifact |
| Schema drift and checksum mismatch fail closed in CI | Public-contract validator and negative tests run in CI | Retain these gates |
| Fixed split traces to human-reviewed evidence | Five-event 2/1/2 split is checksum-pinned and non-overlapping | Named human decisions, official weather context, and evidence links for every formal event |
| Restricted assets remain external | Official captures, generated tensors, private catalogs, and checkpoints use the external data root | Inspect the final archive and record source-specific rights decisions |
| Release documentation names redistributed content | Protocol distinguishes contracts and synthetic fixtures from official captures and model weights | Version-specific release notes and exact artifact inventory |
| Artifact is archival and citable without implying forecast readiness | Existing citation describes software 0.1.6; local source reconstruction was verified | Final dataset release identifier, version-consistent citation, checksums, and documented limitations |

The tracked weather-context and QPE/gauge availability tables each cover only one of the current
five formal event IDs. That entry is still awaiting official context or blocked by missing
event-time QPE. Missing entries are missing status evidence, not proof that no private artifact
exists. Reconcile the tables against all five events before claiming full validation.

Remaining manifest evidence includes reviewed weather regime, machine-readable spatial bounds,
per-event frame availability and checksums, and versioned build provenance. Radar threshold
crossings do not establish a weather mechanism. QPE remains an estimate requiring gauge checks.

The current wheel and sdist are software distributions: they omit the dataset protocol, event
manifest, public-contract validator, and test fixtures. A dataset-protocol source archive must
include those inputs separately, with verification commands and checksums. It must not include
private runtime reports or imply that the planned v0.2 dataset milestone is complete.

## Next actions

1. Investigate and human-review the long shadow gaps using retained private evidence.
2. Review eligible candidates and attach official context; preserve separate candidate, reviewed,
   and formal-split states. Broader regime coverage remains tracked in
   [issue #30](https://github.com/KageRyo/MinxiongHydroCast/issues/30).
3. Complete formal-event weather context and event-time QPE/gauge reports.
4. Produce a reproducible, public-safe protocol archive and exercise its clean extraction path.
5. Review rights, release inventory, citation, and versioned dataset evidence before publishing
   the dataset milestone. Model and notification gates remain separate.

See [deployment evidence](deployment_status.md), [dataset protocol](v0.2_dataset_protocol.md),
and [source rights register](data_source_register.md).
