# Decision authority and human override

MinxiongHydroCast automates collection and validation, not public-safety decisions. Government
agencies remain the authority for official warnings, evacuations, road closures, and emergency
instructions.

## Required roles

| Role | Responsibility | Current assignment |
| --- | --- | --- |
| Service owner | Approves operational use, consumers, SLOs, and external exposure | Unassigned |
| Operations maintainer | Deploys, monitors, acknowledges incidents, and performs rollback | Unassigned |
| Data-contract reviewer | Approves upstream schema and source-semantic changes | Unassigned |
| Model reviewer | Approves evaluation evidence, calibration, and model promotion | Unassigned |
| Local decision liaison | Confirms how outputs may support a real local workflow | Unassigned |

One person may hold multiple roles for internal research, but external operational use requires a
named primary and backup for service operations. Role assignments must be recorded outside source
code with contact and escalation details protected from public exposure.

## Decision matrix

| Decision | Automation | Required human authority |
| --- | --- | --- |
| Mark official observations ready | Allowed when all coded gates pass | Data-contract reviewer defines gates |
| Display an upstream official warning | Allowed with attribution and unchanged meaning | Upstream authority owns the warning |
| Publish an experimental rainfall nowcast | Blocked by default | Model reviewer and service owner |
| Publish or notify a flood-risk assessment | Blocked by default | Model reviewer, service owner, local liaison |
| Suppress a downstream notification | Allowed as a safety action | Operations maintainer, with audit reason |
| Override invalid/stale data to healthy | Prohibited | No role may bypass integrity/readiness gates |

## Human override

An operator may stop collection, disable a consumer, suppress notifications, or roll back a
revision when continued operation could mislead users. Every override must record:

- operator identity and timestamp;
- affected service, dataset, or channel;
- reason and evidence;
- intended duration or explicit expiry;
- recovery condition and final disposition.

Overrides are fail-closed. They may reduce availability but may not relabel demo, stale, degraded,
schema-invalid, corrupt, or missing data as healthy. A manual note cannot satisfy the shadow,
coverage, model, or flood-label gates.

## Promotion approval

Before any experimental forecast or flood-risk notification is enabled, the approving roles must
review the exact artifact version, independent-event evaluation, uncertainty, shadow evidence,
communication wording, rollback target, and alert recipient. Approval is tied to that version and
must be repeated after a material data contract, feature, threshold, or model change.
