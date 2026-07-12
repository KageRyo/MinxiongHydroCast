# Single-host operations runbook

This runbook deploys FloodCastMinxiong as localhost-only user services on one Linux x86_64 host.
It keeps all mutable state on a durable volume and stores the API credentials outside the
repository. The deployment is an internal observation service and shadow deployment; it is not an
official warning system.

## Runtime layout

The default installation uses:

| Path | Purpose |
| --- | --- |
| `/mnt/8tb_hdd/ryo/floodcast-minxiong` | Durable runtime, snapshots, TSDBs, backups, and runner |
| `~/.local/share/floodcast-minxiong` | Stable symlink used by user units |
| `~/.config/floodcast-minxiong/env` | Mode `0600` API-key environment file |
| `~/.config/systemd/user` | Installed user units and timers |

The repository `.env` is an installation input only. It remains ignored by Git and is copied to
the private systemd environment path without printing its values.

## Install the host

From the repository root, run:

```bash
deploy/single-host/install-user-host.sh --env-file .env
sudo loginctl enable-linger "$USER"
```

The installer refuses tracked, staged, or untracked source changes so the deployed revision is
reproducible. It records the Git commit and installed Python package set under the durable
`config/` directory.

The second command is required once. Without linger, user services may stop after the last login
session ends. The installer pins Prometheus and Alertmanager release versions, verifies their
published SHA-256 files, validates all monitoring configs, installs the Python project in a
dedicated virtual environment, and starts:

- the localhost API and operator view on `127.0.0.1:8180`;
- Prometheus on `127.0.0.1:9090`;
- Alertmanager on `127.0.0.1:9093`;
- the local alert audit receiver on `127.0.0.1:9087`;
- collection every ten minutes, shadow evaluation hourly, and backup daily.

Inspect the deployment without exposing credentials:

```bash
systemctl --user list-timers 'floodcast-minxiong-*'
systemctl --user --no-pager --full status floodcast-minxiong-api.service
curl --fail http://127.0.0.1:8180/healthz
curl --fail http://127.0.0.1:8180/readyz
curl --fail http://127.0.0.1:9090/-/ready
curl --fail http://127.0.0.1:9093/-/ready
```

Use `journalctl --user -u UNIT` for service logs. The API, Prometheus, Alertmanager, and receiver
bind to loopback intentionally. Put authentication and TLS at a reverse proxy before allowing
network access.

## Alert routing and drill

Prometheus evaluates `deploy/prometheus/floodcast.rules.yml`. Alertmanager sends firing and
resolved notifications to the durable local receiver. The receiver validates the webhook contract
and appends each delivery to:

```text
/mnt/8tb_hdd/ryo/floodcast-minxiong/notifications/alerts.jsonl
```

The local receiver proves alert generation, routing, and durable delivery. It is not a human
notification channel. Add an organization-owned email, Slack, LINE, PagerDuty, or equivalent
receiver to `alertmanager.yml` only after its secret and named on-call owner are available; keep
that secret out of Git.

Run a local end-to-end drill:

```bash
~/.local/share/floodcast-minxiong/bin/amtool \
  --alertmanager.url=http://127.0.0.1:9093 \
  alert add FloodCastDrill severity=warning service=floodcast-minxiong \
  --annotation=summary='FloodCastMinxiong notification drill'
sleep 12
tail -n 1 ~/.local/share/floodcast-minxiong/notifications/alerts.jsonl
~/.local/share/floodcast-minxiong/bin/amtool \
  --alertmanager.url=http://127.0.0.1:9093 \
  alert add FloodCastDrill severity=warning service=floodcast-minxiong \
  --end="$(date --iso-8601=seconds)"
```

## Backup and restore drill

The daily timer creates a compressed archive beside a Pydantic-validated metadata sidecar. Backup
creation holds the collector lock and verifies every retained manifest and dataset checksum before
writing the archive. Restore rejects links, path traversal, checksum mismatches, existing targets,
and snapshots that fail integrity verification.

Create, verify, and restore a fresh backup:

```bash
systemctl --user start floodcast-minxiong-backup.service
archive="$(find ~/.local/share/floodcast-minxiong/backups -name '*.tar.gz' -printf '%T@ %p\n' \
  | sort -n | tail -n 1 | cut -d' ' -f2-)"
~/.local/share/floodcast-minxiong/venv/bin/floodcast-minxiong-backup \
  verify --archive "$archive"
target="$HOME/.local/share/floodcast-minxiong/restore_drills/$(date +%Y%m%dT%H%M%S)"
~/.local/share/floodcast-minxiong/venv/bin/floodcast-minxiong-backup \
  restore --archive "$archive" --target "$target"
test -f "$target/restore_report.json"
```

The drill target is separate from live operations and must never replace the active store during a
routine test. The daily retention window is 30 days. A second storage device or remote backup is
still required to protect against loss of the entire host or mounted volume.

## Host-bound official contract

WRA rainfall-warning credentials can be restricted by source host. Install the repository runner
only after the base runtime is healthy:

```bash
deploy/single-host/install-actions-runner.sh
systemctl --user --no-pager status floodcast-minxiong-runner.service
```

The installer obtains a short-lived registration token through the authenticated `gh` session,
verifies the official runner asset digest, and applies the `floodcast-minxiong` label. The workflow
runs only by schedule or manual dispatch. CWA and public WRA IoW checks stay on GitHub-hosted
runners; only the WRA warning check runs on this dedicated host.

## Seven-day shadow gate

The collector timer is the source of live attempts. The hourly shadow timer writes its report even
while the gate is blocked. Inspect current evidence at:

```bash
curl --fail http://127.0.0.1:8180/api/v1/shadow-readiness
```

Do not edit `shadow_evidence.json` merely to pass the gate. After a real heavy-rain period, add the
official source reference, exact time window, reviewer identity, and `confirmed: true` only after
manual review. The gate requires seven elapsed days, at least 900 live attempts, success/readiness
rates, gap and integrity limits, and continuous ready coverage of at least one confirmed heavy-rain
period. The eight-day audit window allows the hourly evaluator to measure a full seven-day span
without requiring attempts to land exactly on both window boundaries. A missing qualifying weather
event means the deployment must continue beyond seven days.

The pull request remains draft while this gate is accumulating or any operational drill is
unresolved. Convert it to ready for review only after the report says `shadow_gate_passed=true` and
the workflow, services, alert drill, and restore drill are all healthy.
