# Dataset milestone acceptance

This record tracks [issue #31](https://github.com/KageRyo/MinxiongHydroCast/issues/31).
Verification dated 2026-10-15 covers the source contracts and synthetic reconstruction path;
it does not certify a released official dataset or forecast readiness.

Scope correction, 2026-10-20: human annotations are unavailable. This milestone publishes the
label-free radar-building protocol, automatically derived temporal targets, source inventories
and synthetic reconstruction. It does not certify a weather-labeled corpus. The earlier named
human-review prerequisite is replaced by explicit unknown regimes and reproducible source/split
provenance; missing QPE and legacy acquisition limits remain disclosures. See the checksum-pinned
`data/samples/label_free_protocol_policy.json` and the [protocol](v0.2_dataset_protocol.md).

| Acceptance criterion | Evidence | Remaining work |
| --- | --- | --- |
| Clean checkout validates the manifest and rebuilds synthetic tensors | Fresh Python 3.13 environment; public-contract validation and 90 relevant tests passed, including synthetic CWA grids, sliding tensors, and NPZ round trips | Keep reproducible commands and verification outputs with the release artifact |
| Schema drift and checksum mismatch fail closed in CI | Public-contract validator and negative tests run in CI | Retain these gates |
| Fixed split traces to reproducible source evidence | Five-event 2/1/2 split is checksum-pinned and non-overlapping; frame inventory and official context are linked | Keep weather regimes unknown and annotation availability explicit; do not require unavailable manual labels |
| Restricted assets remain external | Official captures, generated tensors, private catalogs, and checkpoints use the external data root | Inspect the final archive and record source-specific rights decisions |
| Release documentation names redistributed content | Protocol distinguishes contracts and synthetic fixtures from official captures and model weights | Version-specific release notes and exact artifact inventory |
| Artifact is archival and citable without implying forecast readiness | Software citation and protocol-source checksums are separate from a released official dataset | Final dataset release identifier, dataset citation, and reviewed limitations |

The 2026-10-20 reconciliation gives every formal event an explicit weather-context and QPE/gauge
status entry. A subsequent source audit preserved a CWA July report, the official Bavi typhoon
record, and five CODiS Minxiong hourly reports. All five events now link official context and
single-station observations; classification and named human review remain pending. The 36 complete
hourly accumulation intervals inside the event windows are covered at C0M760. This does not
establish areal rainfall, inundation or QPE/gauge agreement.

The authenticated live-source control passed, but ten bounded historical probes (one gauge and
one QPE request per event, at start plus 30 minutes) returned HTTP 404. This establishes only the
tested endpoints and timestamps at collection time, not absence from all official archives. The
new audit is separate from older July probes; CODiS supplied station observations despite these
historyAPI responses. Matched historical QPE grids and validation reports remain unavailable.

`data/samples/formal_event_inventory.json` now records all five events' 221 preserved radar frames,
their source times, credential-free acquisition URLs, sizes, SHA-256 values, split membership,
and machine-readable radar-grid bounds. All 251 external dataset artifacts passed a new size and
checksum verification on 2026-10-20. Each frame header also matched its collection time and the
shared grid. The inventory has its own checksum companion and CI consistency checks against the
unchanged formal split. Bounds describe the outermost TWD67 radar grid-point centers, not a flood
footprint or a WGS84 township boundary. `dataset_release_ready=false` remains explicit.

`data/samples/formal_event_source_audit.json` pins the new source metadata and aggregate station
results. `data/samples/formal_build_provenance.json` records the preserved run and training
parameters, including its original `verify_tls=false`. An exact historical command line and code
revision were not retained and are not invented here. Later checksums do not retroactively
authenticate the original download. A new verified build or independent authenticated copies,
with explicit command/configuration and revision, are required to remove that provenance gap.

Reviewed weather regimes, human decisions, matched formal QPE/gauge validation and complete
historical acquisition provenance are unavailable. They are limitations of this label-free
protocol, not reasons to wait for manual labels. Radar threshold crossings do not establish a
weather mechanism. QPE remains an estimate requiring gauge checks for rainfall accuracy claims. See the
[external evidence assessment](external_disaster_evidence.md) for historical disaster sources and
their limits for the 2026 formal events, and the
[release closure checklist](dataset_release_checklist.md) for concrete remaining work.

The wheel and sdist are software distributions: they omit the dataset protocol, event
manifest, public-contract validator, and test fixtures. A dataset-protocol source archive must
include those inputs separately, with verification commands and checksums. The
[protocol archive commands](v0.2_dataset_protocol.md#reproduce-the-credential-free-contract-checks)
and CI now provide this source reconstruction path. The source archive excludes private runtime
reports and does not imply that the planned v0.2 dataset milestone is complete.

## Next actions

1. Publish the five formal events as radar-selected, unannotated windows with their existing
   source/frame checksums, official context and acquisition limitations.
2. Preserve candidate reports and optional curated review separately; unavailable manual labels
   do not block protocol publication.
3. Report missing formal QPE/gauge validation explicitly without substituting candidate results.
4. Retain CI verification of the protocol archive's clean extraction and synthetic reconstruction.
5. Finalize the exact metadata/code/fixture archive inventory, attribution, separate protocol
   citation and version identifier. Raw official files remain excluded. Model and notification
   gates remain separate.

See [deployment evidence](deployment_status.md), [dataset protocol](v0.2_dataset_protocol.md),
and [source rights register](data_source_register.md).
