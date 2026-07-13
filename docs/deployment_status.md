# Deployment status

This page records verified deployment evidence. It is not a release approval or a claim that
MinxiongHydroCast is an official warning system.

## Verified on 2026-07-13

The single-host shadow deployment is running on Linux host `RTX4090` with user-systemd linger
enabled. Mutable state is stored under `/mnt/8tb_hdd/ryo/minxiong-hydrocast`, and the stable
service path is `~/.local/share/minxiong-hydrocast`. Its private environment file has mode `0600`
and is not tracked by Git.

Verified runtime components:

- collector timer every ten minutes, with strict CWA/WRA API sources;
- localhost API and operator view on `127.0.0.1:8180`;
- Prometheus 3.13.1 on `127.0.0.1:9090`, scraping the API target successfully;
- Alertmanager 0.33.1 on `127.0.0.1:9093`;
- Pydantic-validated alert audit receiver on `127.0.0.1:9087`;
- daily backup and hourly shadow-evaluation timers;
- concise `mhc` command dispatcher available through the stable user path;
- dedicated runner `RTX4090-minxiong-hydrocast`, online with the `minxiong-hydrocast` label, for
  source contracts that require host credentials.

The post-migration live snapshot was healthy and ready. It contained a valid empty WRA
rainfall-warning product, 82 CWA rain-gauge observations, 150 WRA IoW flood-sensor observations,
and a ready Minxiong feature row.

## Operational drills

The original `MinxiongHydroCastDrill` and post-migration `MinxiongHydroCastMigrationDrill`
synthetic alerts produced durable local notification audit records. This proves local
Prometheus/Alertmanager routing and receiver persistence; it does not provide a named human
notification channel. An allowlisted, bounded, retrying Discord incoming-webhook backend is
implemented, but the deployed notification environment is deliberately empty pending explicit
activation and assignment of a named owner.

The post-migration backup drill created and SHA-256 verified a 68-snapshot archive. It restored the
archive into an isolated durable drill directory, verified every snapshot, and confirmed that the
restored latest snapshot ID matched the archive metadata.

The manually dispatched Official Live Contracts run `29219192303` passed both jobs:
GitHub-hosted CWA/IoW contracts and the host-bound WRA rainfall-warning contract on the renamed
self-hosted runner.

The complete local suite passed with 237 tests, and Ruff reported no issues.

## Canonical identifier rollout

The canonical identifier rollout is complete. The GitHub repository and local remote, durable
root, stable service link, private environment paths, Python distribution and entry points,
Prometheus rules and live metric prefix, user-systemd units and timers, and self-hosted runner all
use the identifiers defined in [project_identity.md](project_identity.md).

The runtime migration used a same-filesystem directory rename rather than copying state. Before
the move, all 66 retained snapshots passed application-level integrity verification and a fresh
backup was verified. After the move, checksums for all 396 pre-existing immutable snapshot files
matched, and the store continued to 68 healthy attempts without resetting its first observation.
The shadow report retained a 100% success and readiness rate, a 10.283-minute maximum gap, and a
passing storage-integrity check. Historical Prometheus samples remain in the existing TSDB while
the live endpoint exports only the `minxionghydrocast_` prefix.

All canonical services and timers are enabled, old unit files and timer stamps are absent, the API
and operator view return HTTP 200, Prometheus reports its API target up, Alertmanager is ready, and
the runner is listening under its canonical name and label. Discord delivery was not activated by
the migration.

## Active shadow gate

The shadow deployment started on 2026-07-12. At the post-merge verification point it retained 70
successful and ready live attempts over 10.894 hours, with 100% success and readiness and no gap
over 10.283 minutes. The gate remains blocked by design until all of the following are observed
rather than simulated:

- at least 168 hours between the first and last retained live attempt;
- at least 900 attempts in the eight-day audit window;
- at least 99% collection success and 95% readiness;
- no ready-data gap over 30 minutes and no storage-integrity error;
- continuous ready coverage during at least one reviewed, confirmed heavy-rain period.

Promotion to public service or automated risk notification must remain blocked while those
conditions are incomplete. A qualifying heavy-rain period may require the shadow deployment to
run longer than seven calendar days. Internal code, documentation, and identifier changes may
merge independently when their own review and CI checks pass.

## Remaining promotion work

- Explicitly activate the implemented Discord backend only after naming its primary and backup
  on-call owners, then exercise its incident path.
- Before public operational promotion, replicate backups to another device or remote system. This
  is deferred for the current internal localhost stage; the current backup protects snapshots from
  application-level corruption but not loss of the whole host or volume.
- Assign incident ownership and exercise acknowledgement, override, and rollback responsibilities.
- Complete the real shadow gate and local model/label gates before enabling risk notifications.
- Add authenticated TLS ingress only if the localhost service must become network-accessible.
