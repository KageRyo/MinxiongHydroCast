# Historical archive coverage

`mhc data archive-coverage` (software v0.1.8+) reports preserved native radar/QPE coverage without
changing catalogs, deleting files, requesting source URLs or retrying downloads. JSON, terminal
tables and a standalone offline HTML dashboard use the same deterministic report.

```bash
mhc data archive-coverage --demo --format html --output /tmp/hydrocast-coverage.html
mhc data archive-coverage --demo --format table
mhc data archive-coverage --root /external/hydrocast-data \
  --catalog discovery/event_evidence_catalog.json --format json \
  --max-checks 250 --max-entries 10 --output /external/hydrocast-data/exports/coverage.json
```

Open the demo HTML directly in a browser. Native expandable sections show daily counts, missing
intervals, individual checks and classified source attempts. No JavaScript or network connection
is required. Tables scroll within their container on narrow screens; summaries support keyboard
operation. The demo contains an uncaptured time, a corrupt artifact, duplicate timestamps, a changed
grid, all-nodata pixels and recorded 404/authentication/rate-limit/transport failures.

## What the counts mean

Every count is a **scheduled timestamp slot** within an event/product, not a file-list length.
Both window endpoints are included. A timestamp with duplicate references occupies one slot.

| Count | Meaning |
| --- | --- |
| Expected | Inclusive start/end at the declared cadence |
| Present | At least one referenced artifact exists safely inside the data root |
| Size verified | At least one artifact passed its recorded byte count |
| SHA-256 verified | At least one artifact also passed its recorded checksum |
| Usable | Exactly one artifact, passing integrity and all supported structural checks |
| Missing | Confirmed uncaptured slot or referenced file missing |
| Duplicate times | More than one frame reference at the scheduled timestamp; never usable |
| Unchecked | Metadata unavailable/invalid or at least one verification deferred by the budget |

Counts overlap: they are different checks, not mutually exclusive classes. Duplicate slots may
have integrity-verified artifacts but remain unusable. A slot deferred by the budget can be
present without being verified. Missing/corrupt collection metadata yields unknown presence and
unchecked slots; it does not establish that the original raw frames are missing.

Supported structural checks are native CWA `O-A0059-001` dBZ and `O-B0045-001` mm: header time,
product/units, known geographic datum, valid grid geometry, a stable grid signature within the
entry and at least one finite non-nodata pixel. The first usable frame anchors grid consistency.
Known names for the same datum are recognized without reprojection. Structural usability does
not prove rainfall accuracy, model performance, flood depth or forecast publication readiness.
Gauge quality is not inferred from a radar/QPE schedule.

`missing_intervals` joins consecutive confirmed missing slots. Other failures remain visible in
per-slot state and per-day counts. Outside-window/off-cadence records are separate extras and do
not inflate expected or usable counts. Day grouping defaults to `Asia/Taipei`; `--timezone UTC`
or another installed IANA zone changes only the report grouping. Slot timestamps remain UTC.

## Catalog and inventory inputs

`--catalog` accepts three forms. All resolved files, including symlinks and pinned metadata, must
stay under `--root`. Relative catalog paths are root-relative; absolute paths must be inside it.

1. Existing discovery `EventEvidenceCatalog`: candidate windows and configured radar cadence;
   recorded raw-frame hashes and verified event collection metadata supply timestamps. Recorded
   failed evidence captures supply source-attempt categories without exposing error text.
2. Existing `DatasetCatalog`: the checksum-pinned dataset manifest supplies cadence/units/datum;
   verified event collection metadata supplies raw timestamp/path identity. Preserve its manifest
   at the catalog's referenced relative path inside the external root. If a legacy catalog points
   to `data/samples/event_split_manifest.json`, copy the **exact recorded revision** into that
   relative location and verify its recorded checksum first. The reporter never searches outside
   the root or edits hashes to repair provenance.
3. Explicit `ArchiveInventory`, useful for other preserved native radar/QPE collections:

```json
{
  "schema_version": "1.0",
  "kind": "archive_inventory",
  "entries": [{
    "event_id": "research_event_one",
    "data_id": "O-A0059-001",
    "start_time": "2026-07-01T00:00:00Z",
    "end_time": "2026-07-01T00:20:00Z",
    "cadence_minutes": 10,
    "units": "dBZ",
    "crs": "TWD67",
    "frames": [{
      "data_time": "2026-07-01T00:00:00Z",
      "path": "raw/radar/frame.json",
      "bytes": 12345,
      "sha256": "<64 lowercase hexadecimal characters>"
    }],
    "attempts": [{
      "data_time": "2026-07-01T00:10:00Z",
      "attempted_at": "2026-07-01T00:12:00Z",
      "http_status": 404,
      "failure_kind": "http"
    }]
  }]
}
```

All times require a timezone. Repeated event/product entries, impossible cadence windows and
unsupported products are rejected. Preserve collection-time hashes; do not recompute a recorded
hash to make corruption disappear. A missing checksum is explicitly unverified and never usable.
For QPE use `O-B0045-001`, `units: "mm"` and the product's actual declared observation cadence;
the temporal sampling cadence is separate from its past-hour accumulation meaning.

Source attempts distinguish HTTP 404, authentication (401/403), rate limits (429), transport,
other HTTP and unknown errors. Event/product/time, attempt index and input SHA preserve traceability.
Original URL/error strings and host paths are omitted. A tested URL returning 404 does **not**
establish upstream retention policy. No retry executor or retry plan is included; acquisition
remains a separate explicit use of existing ingestion commands and their bounded retry options.

## Bounds and outputs

Defaults verify at most **250 raw frame references** across the first **10 event/product entries**.
`--max-checks 0` reports presence while leaving every raw frame unverified. Hard maxima are 10,000
checks and 100 included entries, with at most 100,000 scheduled slots. Pinned metadata verification
is additional bounded work for included entries. Omitted entries and deferred checks are explicit;
these limits do not imply a complete archive-wide assessment. Files/catalogs should be stable
while a snapshot is generated. Checksums provide integrity, not acquisition authentication.

Without `--output`, JSON/table reports go to stdout. HTML requires a new `.html` output. Explicit
outputs must be new `.json`, `.txt` or `.html` files matching `--format`, below the data or system
temporary root and outside project source. Existing files are never overwritten. Output creation
is the only write; source artifacts, formal splits and catalogs stay unchanged. Reports omit
private locations but still contain event/source metadata, so review sharing permissions.
