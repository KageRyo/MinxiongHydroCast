# Dataset release closure checklist

This checklist is for [issue #31](https://github.com/KageRyo/MinxiongHydroCast/issues/31).
It does not require 10 positive / 20 negative flood labels, a trained model promotion,
an operational shadow pass or a public forecast endpoint. Those gates remain separate.
The current dataset protocol still requires reviewed official context and matched QPE/gauge
evidence; this checklist does not waive them.

## Collected evidence for the fixed formal split

The [CWA July report](https://www.cwa.gov.tw/Data/climate/Watch/report/report_202607.pdf),
printed page 1, gives dated synoptic context. The
[Bavi record](https://rdc28.cwa.gov.tw/TDB/public/typhoon_detail?typhoon_id=202609)
provides the official warning interval. These were downloaded over verified TLS and preserved
externally with checksums. The monthly report's PDF creation date is not treated as its publication
date. Context source availability is distinct from a reviewer's final causal classification.

| Formal event window (Taiwan time) | Official context collected | C0M760 complete hourly intervals | Station sum / peak hour (mm) | Remaining review |
| --- | --- | --- | --- | --- |
| July 7, 04:00–12:00, train | July report's July 1–8 Pacific High annotation | 8 / 8 | 0 / 0 | Local mechanism and label |
| July 10, 10:00–20:00, train | July report's July 10–11 Bavi annotation and typhoon record | 10 / 10 | 0 / 0 | Local mechanism and label |
| July 9, 16:00–22:00, validation | Bavi sea-warning interval begins July 9 at 14:30 | 6 / 6 | 0 / 0 | Local mechanism; warning interval alone does not establish local effects |
| July 3, 13:00–19:00, test | July report's July 1–8 Pacific High annotation | 6 / 6 | 7 / 5.5 | Local mechanism and label |
| July 11, 00:00–06:00, test | July report's July 10–11 Bavi annotation and typhoon record | 6 / 6 | 16.5 / 6 | Local mechanism and label |

Station sums cover only full one-hour intervals within each event; they are not township-wide
rainfall, flood labels or confirmed heavy-rain periods. Each hourly value had a non-negative
accumulation and no quality flag. Traceable metadata, source checksums, request parameters and
probe times are in `data/samples/formal_event_source_audit.json`; the raw series remain external.
Current station metadata identifies Minxiong C0M760 at WGS84 120.428457 E, 23.551754 N. Historical
relocation information has not been independently checked.

## What must happen before closing #31

| Item | Current state | Concrete next action |
| --- | --- | --- |
| Fixed manifest, frame inventory and synthetic reconstruction | Implemented and CI checked | Preserve them in the release packet and record final revision/checksums |
| Named human review for every formal event | Sources collected; decisions pending | Inspect the official context, radar and gauge evidence; record identity, decision, time, evidence locators and retained limitations; do not infer approval from collection |
| Event-time QPE/gauge validation | CODiS observations collected; matched QPE missing | Obtain official O-B0045-001 historical grids for these windows or document another approved official archive; align accumulation intervals, datum, station location and quality flags before running validation |
| Acquisition and build provenance | Historical run retained, with TLS verification disabled and exact command/revision absent | Preserve those limits; independently authenticate the old source copies or acquire new verified copies and record the build command/configuration, revision and artifact inventory |
| Rights and redistribution inventory | Official platform rules collected; owner decision pending | Decide each source's attribution and each artifact's redistribution boundary; leave original captures external unless separately approved |
| Archival version and citation | Software v0.1.7 citation exists; dataset milestone unreleased | Publish the reviewed protocol artifact with exact contents, checksum inventory, limitations, dataset citation and stable release identifier; do not invent a DOI or release date |

The five July windows comprise 221 cadence-aligned radar timestamps. An official archive inquiry
can request matching O-B0045-001 past-one-hour QPE grids at 10-minute cadence, or at minimum the
36 hourly interval ends represented by the collected gauge evidence. Request numeric grids and
their nodata, coordinate datum, timestamp/accumulation definitions and quality metadata; images
alone cannot be substituted. The [official application service](https://hdps.cwa.gov.tw/static/applyform.html)
is an available request route; no application has been submitted on the project's behalf.

Ten authenticated historyAPI probes returned HTTP 404 at event start plus 30 minutes. A successful
live-source authentication control distinguishes these results from an invalid key, but does not
establish the retention policy or completeness of other archives. CODiS is a working alternative
for station observations, not for missing QPE grids.

If old windows cannot obtain enough reviewed evidence, a separately approved split proposal may
use newly collected candidates with complete synchronized sources and official context. That
proposal must preserve independent splits and rerun the unchanged validation gates; silently
relabeling the five legacy events is not an acceptable shortcut.

## Preserved candidate fallback, verified 2026-10-20

The fallback now has collected evidence: 59 distinct QPE/gauge capture pairs across 35
candidates (34 pending and one rejected) have matching observation times and completed
source-consistency reports. Every source pair passed its recorded byte-count and SHA-256
checks. The public, checksum-pinned aggregate is
`data/samples/candidate_qpe_validation_summary.json`; detailed reports and candidate IDs remain
in the external research store.

The grids declare TWD67 geographic coordinates, while preserved normalized gauges use WGS84.
The diagnostic used official paired station coordinates only when station ID and both preserved
WGS84 coordinates agreed within 0.000001 degree. It selected the official native TWD67 pair;
307 station observations without a verified pair were excluded. No approximate datum shift was
applied. Each of the 59 reports retains at least one matched station. Because this QPE product
already incorporates gauge correction, these are consistency checks, not independent accuracy
estimates. Exact paired captures also do not cover each complete event window.

Five pending, non-overlapping candidates were shortlisted using local gauge rainfall. All 454
referenced artifacts, including 219 radar frames, passed checksum and size verification. Their
16 exact paired captures and preserved official July, August and September reports are assembled
with blank review decisions in an external review proposal. The largest observed Minxiong
single-station hourly accumulation in this shortlist was 46 mm; this does not establish township
flooding or approve an event's weather regime. No human decisions or formal split changes were
added. This provides a concrete review route while the legacy windows' historical QPE remains
unavailable at the tested URLs.

The validator now requires timezone-aware equal accumulation end times and the same declared
geographic datum before matching. Raw official station payloads can supply paired native
coordinates; normalized WGS84 gauges cannot be compared directly to TWD67 grids. Missing or
incompatible metadata yields exclusions. Previously generated reports must be rerun with these
checks before use as acceptance evidence. For compatible source payloads:

```bash
python -m minxionghydrocast.pipelines.qpe_gauge_validation \
  --qpe-grid /external/capture/qpe.xml \
  --gauge-json /external/capture/gauges.json \
  --event-id review_candidate \
  --output /external/reports/qpe_gauge_validation.json
```

See [dataset acceptance](dataset_acceptance.md), [dataset protocol](v0.2_dataset_protocol.md)
and [source rights register](data_source_register.md).
