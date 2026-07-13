# Incident response

This runbook applies to the supervised internal observation service. A named primary operator and
backup operator must be assigned before the service is exposed beyond localhost or used in an
external operational workflow.

## Severity

| Severity | Examples | Initial response target |
| --- | --- | --- |
| Critical | API down, collector repeatedly failing, corrupt snapshot, credential compromise | 15 min |
| High | Required dataset stale, Minxiong coverage missing, official contract drift | 30 min |
| Medium | Degraded fallback, notification delivery failure, backup failure | 4 hours |
| Low | Research pipeline failure with no operational impact | Next working day |

Targets are internal objectives, not a public service-level agreement.

## First response

1. Acknowledge the alert and record the operator, start time, and affected component.
2. Check `GET /healthz`, `GET /readyz`, and `GET /api/v1/status` on the localhost API.
3. Inspect the relevant user unit with `systemctl --user status` and `journalctl --user -u`.
4. Preserve the latest failed-attempt manifest, run summary, and relevant redacted logs.
5. Confirm that no demo, fallback, stale, or corrupt data was exposed as ready.
6. Decide whether to retry, disable a consumer, rotate a secret, or invoke rollback.

## Incident-specific actions

### Official source or schema failure

- Run the source-specific contract smoke command.
- Distinguish authentication, rate limit, transport, upstream HTTP, and schema drift.
- Do not weaken strict schema validation to restore a green status.
- Treat scraper fallback as degraded and not ready.
- Record the upstream dataset ID, redacted URL, fetch time, and adapter schema version.

### Stale or missing observations

- Compare source production time, observation time, fetch time, and configured freshness limit.
- Check whether the failure affects all of Chiayi County or only required Minxiong coverage.
- Do not replace a missing observation with a model estimate.

### Storage or integrity failure

- Stop the collector timer before manipulating the operational store.
- Preserve the affected snapshot and checksum evidence.
- Verify the latest backup before any restore attempt.
- Restore into an isolated target and validate it before changing the active store.

### Notification failure

- Confirm Alertmanager readiness and the durable local alert audit first.
- Inspect the redacted provider delivery log; never paste a webhook URL into an incident record.
- Rotate the Discord webhook immediately if its URL may have been exposed.
- A notification failure does not make stale or invalid data ready.

## Resolution

An incident is resolved only after the failing component is healthy, readiness semantics are
correct, missed data or alert gaps are documented, and a follow-up collection succeeds. For
critical and high incidents, record root cause, detection gap, recovery evidence, and a concrete
preventive action. Do not erase failed-attempt manifests or audit records after resolution.
