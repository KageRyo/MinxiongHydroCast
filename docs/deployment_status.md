# Deployment status

This page records verified deployment evidence. It is not a release approval or a claim that
FloodCastMinxiong is an official warning system.

## Verified on 2026-07-12

The single-host shadow deployment is running on Linux host `RTX4090` with user-systemd linger
enabled. Mutable state is stored under `/mnt/8tb_hdd/ryo/floodcast-minxiong`; the stable service
path is `~/.local/share/floodcast-minxiong`. The private environment file has mode `0600` and is
not tracked by Git.

Verified runtime components:

- collector timer every ten minutes, with strict CWA/WRA API sources;
- localhost API and operator view on `127.0.0.1:8180`;
- Prometheus 3.13.1 on `127.0.0.1:9090`, scraping the API target successfully;
- Alertmanager 0.33.1 on `127.0.0.1:9093`;
- Pydantic-validated alert audit receiver on `127.0.0.1:9087`;
- daily backup and hourly shadow-evaluation timers;
- dedicated GitHub Actions runner `RTX4090-floodcast-minxiong` with the
  `floodcast-minxiong` label.

The initial live snapshot was healthy and ready. It contained a valid empty WRA rainfall-warning
product, 81 CWA rain-gauge observations, 150 WRA IoW flood-sensor observations, and a ready
Minxiong feature row.

## Operational drills

The `FloodCastDrill` synthetic alert produced both firing and resolved deliveries in the durable
notification JSONL log. This proves local Prometheus/Alertmanager routing and receiver persistence;
it does not provide a named human notification channel. An allowlisted, bounded, retrying Discord
incoming-webhook backend is implemented but remains disabled until an operator places a webhook URL
in the ignored host environment file.

The backup drill created and SHA-256 verified
`floodcast-minxiong-20260712T234326+0800.tar.gz`. It restored three snapshots into an isolated
durable drill directory, verified every snapshot, and confirmed that the restored latest snapshot
ID matched the archive metadata.

The manually dispatched
[Official Live Contracts run](https://github.com/KageRyo/FloodCastMinxiong/actions/runs/29198834843)
passed both jobs: GitHub-hosted CWA/IoW contracts and the host-bound WRA rainfall-warning contract.

The complete local suite passed with 221 tests, and Ruff reported no issues.

## Active shadow gate

The shadow deployment started on 2026-07-12. Its early audit reported three successful and ready
live attempts with 100% success and readiness. The gate remains blocked by design until all of the
following are observed rather than simulated:

- at least 168 hours between the first and last retained live attempt;
- at least 900 attempts in the eight-day audit window;
- at least 99% collection success and 95% readiness;
- no ready-data gap over 30 minutes and no storage-integrity error;
- continuous ready coverage during at least one reviewed, confirmed heavy-rain period.

The pull request must remain draft while those conditions are incomplete. A qualifying heavy-rain
period may require the shadow deployment to run longer than seven calendar days.

## Remaining promotion work

- Configure the implemented Discord backend with an organization-owned channel, name its on-call
  owner, and exercise its incident path.
- Replicate backups to another device or remote system; the current backup protects snapshots from
  application-level corruption but not loss of the whole host or volume.
- Document incident ownership, acknowledgement, override, and rollback responsibilities.
- Complete the real shadow gate and local model/label gates before enabling risk notifications.
- Add authenticated TLS ingress only if the localhost service must become network-accessible.
