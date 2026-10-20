# Label-free radar dataset-building protocol v0.2.0

Release tag: `dataset-protocol-v0.2.0`

This artifact versions the reproducible source protocol independently of Python software
v0.1.7. Human annotations are unavailable and are not a prerequisite. Prediction targets derive
from future observed radar frames, with no manually assigned weather, disaster or flood labels.
The existing five-event split is unchanged; weather regimes remain unknown.

## Exact contents and citation

The source archive contains committed code and package resources, documentation and its assets,
public sample/evidence records, test fixtures, validators and synthetic reconstruction tests.
It includes the fixed event manifest, 221-frame source inventory, official-context audit,
legacy build provenance and checksum-pinned label-free policy. `PROTOCOL_ARCHIVE.json` records
the immutable source commit/tree; the inner `SHA256SUMS` lists every included file.

Release assets include the source archive, an exact `RELEASE_INVENTORY.json` of paths, byte
counts and SHA-256 values, a separate protocol `CITATION.cff`, and outer `SHA256SUMS`.
Original official captures, private catalogs and reviewer identities, full station/comparison
reports, tensors, checkpoints, credentials and machine deployment paths are excluded.
Source metadata is attributed to Taiwan's Central Weather Administration and the original
official product identifiers. The project's MIT license does not relicense official source data.

Use the [protocol citation](dataset-protocol-v0.2.0.cff) for this artifact; the root citation
continues to describe software v0.1.7. The immutable GitHub tag and source revision identify the
artifact. No DOI or third-party archive registration is claimed.

## Verification

The PR's CI runs strict public contracts, Python 3.11/3.13 tests, archive reconstruction,
package checks and documentation validation. Release preparation verifies the committed archive,
extracts it to a new directory and reruns synthetic reconstruction/public-contract tests.
Download from the trusted repository release; checksums establish integrity, not authorship.

```bash
python scripts/protocol_archive.py verify \
  --archive /path/to/minxiong-hydrocast-dataset-protocol-v0.2.0.tar.gz \
  --extract-to /tmp/mhc-protocol-v020
cd /tmp/mhc-protocol-v020
python scripts/validate_public_contracts.py
python -m pytest -q tests/test_public_contracts.py tests/test_event_splits.py \
  tests/test_dataset_build.py tests/test_radar_tensor_conversion.py \
  tests/test_qpe_gauge_validation.py
```

Install the archived dependencies as described in the [protocol](../v0.2_dataset_protocol.md).
The reconstruction uses synthetic fixtures and does not require API credentials or live downloads.

## Retained limitations

Official reports provide broad weather context rather than local causal labels. Legacy event
names containing "heavy-rain" describe radar selection, not verified areal rainfall or flooding.
Matched historical QPE is missing at the tested URLs. The 59 preserved candidate comparisons
are source-consistency diagnostics for gauge-corrected QPE, not independent rainfall truth or
validation of the five formal events. The old corpus acquisition used `verify_tls=false` and did
not preserve the exact command/revision; later checksums do not repair that provenance.

These limits remain explicit in the source artifact. Its `dataset_milestone_complete=false`
records that a fully curated/authenticated corpus is not certified, while this release delivers
the label-free building method and its reproducible contracts. Forecast publication and the
existing curated candidate-promotion/model/alert gates are unchanged.
