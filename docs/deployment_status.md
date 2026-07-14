# Deployment status

This page records verified deployment evidence. It does not claim that MinxiongHydroCast is an
official warning system or authorize external operational use.

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

## Continuous event evidence rollout verified on 2026-07-14

PR #12 deployed the continuous event-evidence workflow from merge revision
`7f8fccc8f93a5261dab6be47550b9b11d5f9b25a`. The recorded installed revision matched `main`, the
private systemd environment remained mode `0600`, and
`MINXIONGHYDROCAST_RESEARCH_ROOT` resolved to the external durable research volume.

The `minxiong-hydrocast-event-discover.timer` was enabled and active on a 20-minute schedule. Its
first installed oneshot completed successfully after scanning 33 new frames and triggers. The
12:00 run summary was also `status=ok`, reported no evidence errors, and incrementally scanned two
new trigger frames without changing any formal dataset split.

At the 2026-07-14 12:00 evidence snapshot, the strict catalog contained one active candidate:

- 82 of 88 required 10-minute radar frames were captured;
- 76 trigger frames extended the candidate through 11:50, with a provisional window end at 12:50;
- 18 synchronized evidence captures each reported QPE/gauge/warning states `ok/ok/empty`;
- full catalog artifact verification reported zero checksum or size errors;
- review state remained `collecting`, `pending`, `unclassified`, and `not_added`.

These counts are a dated operational snapshot, not a completion claim. The rolling window must
first stop extending and reach `awaiting_review`. A reviewer must then attach official weather
context before assigning a regime. The formal five-event split remained unchanged with SHA-256
`953b8b0d85b0269adcc7468288332e039d01512a0ac626090efbf56b12a6a6e1`.

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

The original deployment suite passed with 237 tests. The continuous event-evidence rollout later
passed 268 tests in PR CI, and Ruff reported no issues.

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

External operational use and automated risk notification must remain disabled while those
conditions are incomplete. A qualifying heavy-rain period may require the shadow deployment to
run longer than seven calendar days. Internal code, documentation, and identifier changes may
merge independently when their own review and CI checks pass.

## Outstanding safeguards

- Let the active candidate finish its post-trigger window, review its radar/QPE/gauge/warning
  evidence and official weather context, and record the first auditable `mhc event-review`
  decision. Approval alone must not add it to a formal split.
- Continue collecting reviewed typhoon, frontal, Mei-yu, and convective regimes. Retraining and
  formal split expansion remain blocked until the dataset is meaningfully more diverse.
- Explicitly activate the implemented Discord backend only after naming its primary and backup
  on-call owners, then exercise its incident path.
- Before any external operational use, replicate backups to another device or remote system. The
  current backup protects snapshots from application-level corruption but not loss of the whole
  host or volume.
- Assign incident ownership and exercise acknowledgement, override, and rollback responsibilities.
- Complete the real shadow gate and local model/label gates before enabling risk notifications.
- Add authenticated TLS ingress only if the localhost service must become network-accessible.
