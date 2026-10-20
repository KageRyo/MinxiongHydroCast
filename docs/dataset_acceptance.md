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

## Published protocol, 2026-10-20

The [dataset-protocol-v0.2.0 release](https://github.com/KageRyo/MinxiongHydroCast/releases/tag/dataset-protocol-v0.2.0)
delivers the corrected label-free scope of #31. Its source commit is
`257ce24ef6c0fcbf4efd1f6192eb568200371b1f`. All five uploaded assets were downloaded again:
outer checksums, all 263 archive member sizes/digests, source commit and pinned split were
verified; 62 reconstruction/public-contract tests passed from that downloaded extraction.
The source PR passed all 382 tests and Python 3.11/3.13 CI, archive, package, documentation,
CodeQL and SonarCloud checks before merge.

The archive SHA-256 is
`7c4e261fa1417d21a003f42eca01548497e608b80fc64f7ec31019d71d031a74`.
Release assets provide the exact inventory, separate citation, notes and outer checksums.
No DOI or certified official corpus is claimed. The label-free protocol acceptance is complete;
the acquisition and annotation limitations below remain limitations rather than pending labels.

| Acceptance criterion | Evidence | Status |
| --- | --- | --- |
| Clean checkout validates the manifest and rebuilds synthetic tensors | CI plus 62 tests from the downloaded release extraction | Passed |
| Schema drift and checksum mismatch fail closed in CI | Public-contract validator and negative tests run in CI | Passed |
| Fixed split traces to reproducible source evidence | Five-event 2/1/2 split is checksum-pinned and non-overlapping; source/frame inventory and official context are linked; unknown regimes are explicit | Passed for label-free scope |
| Restricted assets remain external | Exact 263-file inventory and prepublication path/credential-pattern scan; original captures, private catalogs, tensors and checkpoints excluded | Passed for protocol artifact |
| Release documentation names redistributed content | Published release notes and per-file sizes/digests; source attribution and exclusion boundaries | Passed |
| Artifact is archival and citable without implying forecast readiness | Independent protocol tag, immutable source commit, separate CITATION.cff, inner/outer checksums and retained limitations | Published |

The 2026-10-20 reconciliation gives every formal event an explicit weather-context and QPE/gauge
status entry. A subsequent source audit preserved a CWA July report, the official Bavi typhoon
record, and five CODiS Minxiong hourly reports. All five events now link official context and
single-station observations; human annotations are unavailable and weather regimes stay unknown. The 36 complete
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
reports. The source-protocol release completes the label-free deliverable, while a fully
curated/authenticated corpus and forecast readiness are not certified.

## Maintenance and separate corpus improvements

1. Preserve the published five formal events as radar-selected, unannotated windows with their existing
   source/frame checksums, official context and acquisition limitations.
2. Preserve candidate reports and optional curated review separately; unavailable manual labels
   do not block protocol publication.
3. Report missing formal QPE/gauge validation explicitly without substituting candidate results.
4. Retain CI verification of the protocol archive's clean extraction and synthetic reconstruction.
5. Preserve the published metadata/code/fixture archive inventory, attribution, separate protocol
   citation and version identifier. Raw official files remain excluded. Model and notification
   gates remain separate.

See [deployment evidence](deployment_status.md), [dataset protocol](v0.2_dataset_protocol.md),
and [source rights register](data_source_register.md).
