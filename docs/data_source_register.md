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
| CWA file/history APIs | CWA | Radar/QPE discovery and event archives | API key | Research dataset construction | Pending model-distribution rights review |
| WRA public web pages | WRA | Managed fallback diagnostics | Public web | Degraded and never ready | Not approved as primary source |
| Shelters, pumps, risk areas | Respective publisher | Optional location reference | Operator-supplied files | Snapshot-copied after review | Source-specific review required |
| Local flood labels | Evidence owner | Model evaluation and calibration | Private reviewed manifest | Never committed; provenance required | Consent/privacy review required |

## Source acceptance record

Each production source needs a recorded owner approval covering:

- authoritative dataset identifier and semantic meaning;
- authentication and permitted access method;
- expected publication cadence and measured retention;
- attribution and redistribution requirements;
- storage duration and deletion obligations;
- personal, location, or emergency-information sensitivity;
- approved operational and research uses.

Until that record is approved, data may support internal engineering and validation only. A source
being technically public does not by itself approve unrestricted redistribution or public alerts.

## Change control

Endpoint, schema, unit, coordinate, cadence, or licensing changes require a new contract review.
Adapters must fail closed on schema drift. Preserve a minimized, non-sensitive fixture and contract
test for technical changes; preserve the external approval record separately from the repository.
