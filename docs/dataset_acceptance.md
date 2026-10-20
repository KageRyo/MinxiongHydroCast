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
| Artifact is archival and citable without implying forecast readiness | Software citation and protocol-source checksums are separate from a released official dataset | Final dataset release identifier, dataset citation, and reviewed limitations |

The 2026-10-20 reconciliation gives every formal event an explicit weather-context and QPE/gauge
status entry. Four newly recorded gaps remain unverified; the older July 3 entry still awaits
official context and is blocked by missing event-time QPE. This is complete status coverage, not
completed validation. Older HTTP 404 probes are not attributed to the four unprobed windows.

`data/samples/formal_event_inventory.json` now records all five events' 221 preserved radar frames,
their source times, credential-free acquisition URLs, sizes, SHA-256 values, split membership,
and machine-readable radar-grid bounds. All 251 external dataset artifacts passed a new size and
checksum verification on 2026-10-20. Each frame header also matched its collection time and the
shared grid. The inventory has its own checksum companion and CI consistency checks against the
unchanged formal split. Bounds describe the outermost TWD67 radar grid-point centers, not a flood
footprint or a WGS84 township boundary. `dataset_release_ready=false` remains explicit.

Remaining manifest evidence includes reviewed weather regime, human decisions and evidence links,
and versioned build-command provenance. Radar threshold crossings do not establish a weather
mechanism. QPE remains an estimate requiring gauge checks. See the
[external evidence assessment](external_disaster_evidence.md) for historical disaster sources and
their limits for the 2026 formal events.

The wheel and sdist are software distributions: they omit the dataset protocol, event
manifest, public-contract validator, and test fixtures. A dataset-protocol source archive must
include those inputs separately, with verification commands and checksums. The
[protocol archive commands](v0.2_dataset_protocol.md#reproduce-the-credential-free-contract-checks)
and CI now provide this source reconstruction path. The source archive excludes private runtime
reports and does not imply that the planned v0.2 dataset milestone is complete.

## Next actions

1. Investigate and human-review the long shadow gaps using retained private evidence.
2. Review eligible candidates and attach official context; preserve separate candidate, reviewed,
   and formal-split states. Broader regime coverage remains tracked in
   [issue #30](https://github.com/KageRyo/MinxiongHydroCast/issues/30).
3. Complete formal-event weather context and event-time QPE/gauge reports.
4. Retain CI verification of the protocol archive's clean extraction and synthetic reconstruction.
5. Review rights, release inventory, citation, and versioned dataset evidence before publishing
   the dataset milestone. Model and notification gates remain separate.

See [deployment evidence](deployment_status.md), [dataset protocol](v0.2_dataset_protocol.md),
and [source rights register](data_source_register.md).
