# Data source register

This register documents source purpose and operational treatment. It is not a legal opinion.
Dataset terms, attribution, redistribution, retention, and public-display rights require owner
review before public display, redistribution, or other external operational use.

| Source | Authority | Purpose | Access | Operational treatment | Rights review |
| --- | --- | --- | --- | --- | --- |
| `O-A0002-001` rain gauges | CWA | Live rainfall observations | API key | Required, strict schema and freshness | Pending public-use rights review |
| Rainfall Warning v2 | WRA | Active official rainfall warnings | API key | Required; validated empty is healthy | Pending public-use rights review |
| IoW dataset 142980 | WRA | Flood-depth measurements | Public open-data API | Joined to sensor metadata; strict freshness | Pending public-use rights review |
| IoW dataset 142979 | WRA | Sensor identity and location metadata | Public open-data API | Required for stable sensor semantics | Pending public-use rights review |
| CWA file/history APIs | CWA | Radar/QPE discovery and event archives | API key | Dataset construction | Pending model-distribution rights review |
| WRA public web pages | WRA | Managed fallback diagnostics | Public web | Degraded and never ready | Not approved as primary source |
| Shelters, pumps, risk areas | Respective publisher | Optional location reference | Operator-supplied files | Snapshot-copied after review | Source-specific review required |
| Local flood labels | Evidence owner | Model evaluation and calibration | Private reviewed manifest | Never committed; provenance required | Consent/privacy review required |

## Source acceptance record

### Label-free protocol publication boundary, 2026-10-20

`dataset-protocol-v0.2.0` redistributes the already committed project source, package resources,
documentation/assets, public test fixtures and source/evidence metadata listed in its exact
`RELEASE_INVENTORY.json`. Official source identifiers, URLs, checksums and aggregate findings
are attributed to CWA in the release and preserved audit records. Original official captures,
website PDFs, CODiS series, private catalogs, tensors and checkpoints remain external.
This is a protocol-artifact boundary, not approval to redistribute raw source data, publish
model weights or operate alerts. The source-specific production-use reviews below stay separate.

### Evidence collected on 2026-10-20

The [CWA platform rules](https://opendata.cwa.gov.tw/about/rules) were inspected through the
official frontend's published text (the initial HTML alone is an application shell). The source
defines open data, describes reuse and attribution duties, excludes patent/trademark grants,
and disclaims endorsement. Its attribution appendix identifies CWA and the dataset name. The
retrieved rules script has SHA-256
`82b0d1469ac41d8a5c0db894bef477b8a8ed0d4fd0b8c48c65cf3d8f6134de7e`.

This is collected licensing evidence, not an owner approval or a blanket right to redistribute
every CWA website PDF, CODiS response, model weight or third-party asset. The proposed public
packet contains source references, checksums and aggregate station results; the report PDF,
typhoon-page capture and original hourly observations remain external. Record an explicit
source-and-artifact decision before the dataset release. Attribution for this packet is
"Central Weather Administration, Taiwan — July 2026 climate report, Bavi typhoon database and
CODiS C0M760 hourly observations".

Each production source needs a recorded owner approval covering:

- authoritative dataset identifier and semantic meaning;
- authentication and permitted access method;
- expected publication cadence and measured retention;
- attribution and redistribution requirements;
- storage duration and deletion obligations;
- personal, location, or emergency-information sensitivity;
- approved operational and data-model uses.

Until that record is approved, data may support internal engineering and validation only. A source
being technically public does not by itself approve unrestricted redistribution or public alerts.

## Change control

Endpoint, schema, unit, coordinate, cadence, or licensing changes require a new contract review.
Adapters must fail closed on schema drift. Preserve a minimized, non-sensitive fixture and contract
test for technical changes; preserve the external approval record separately from the repository.
