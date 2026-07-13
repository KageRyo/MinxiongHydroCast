# Single-host operations runbook

This runbook deploys MinxiongHydroCast as localhost-only user services on one Linux x86_64 host.
It keeps all mutable state on a durable volume and stores the API credentials outside the
repository. The deployment is an internal observation service and shadow deployment; it is not an
official warning system.

## Runtime layout

The default installation uses:

| Path | Purpose |
| --- | --- |
| `/mnt/8tb_hdd/ryo/minxiong-hydrocast` | Durable runtime, snapshots, TSDBs, backups, and runner |
| `~/.local/share/minxiong-hydrocast` | Stable symlink used by user units |
| `~/.config/minxiong-hydrocast/env` | Mode `0600` collector API-key environment file |
| `~/.config/minxiong-hydrocast/notifications.env` | Mode `0600` notification-only environment |
| `~/.config/systemd/user` | Installed user units and timers |

The repository `.env` is an installation input only. It remains ignored by Git and is copied to
private systemd environment paths without printing values. The installer separates the optional
Discord URL from the collector credentials so the alert receiver cannot read CWA or WRA keys.

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
- observation collection every ten minutes, radar-event discovery every twenty minutes, shadow
  evaluation hourly, and backup daily.

Inspect the deployment without exposing credentials:

```bash
systemctl --user list-timers 'minxiong-hydrocast-*'
systemctl --user --no-pager --full status minxiong-hydrocast-api.service
systemctl --user --no-pager --full status minxiong-hydrocast-event-discover.service
curl --fail http://127.0.0.1:8180/healthz
curl --fail http://127.0.0.1:8180/readyz
curl --fail http://127.0.0.1:9090/-/ready
curl --fail http://127.0.0.1:9093/-/ready
```

Use `journalctl --user -u UNIT` for service logs. The API, Prometheus, Alertmanager, and receiver
bind to loopback intentionally. Put authentication and TLS at a reverse proxy before allowing
network access.

Event discovery writes only to the external `MINXIONGHYDROCAST_RESEARCH_ROOT`. Its candidate queue
requires human review and never edits the formal dataset split. Inspect the structured summary at
`~/.local/share/minxiong-hydrocast/run_summaries/event_discover.json`; see
[continuous_event_evidence.md](continuous_event_evidence.md) for the artifact and review contract.

## Alert routing and drill

Prometheus evaluates `deploy/prometheus/minxiong-hydrocast.rules.yml`. Alertmanager sends firing and
resolved notifications to the durable local receiver. The receiver validates the webhook contract
and appends each delivery to:

```text
/mnt/8tb_hdd/ryo/minxiong-hydrocast/notifications/alerts.jsonl
```

The local receiver proves alert generation, routing, and durable delivery. It is not a human
notification channel by itself. An optional Discord incoming-webhook delivery backend is included
and disabled when no URL is configured. It uses a webhook rather than a full Discord bot because
one-way monitoring messages do not need a bot token, Gateway connection, or permission to read
channel events.

Create an incoming webhook for the target Discord channel using the
[official Discord webhook documentation](https://docs.discord.com/developers/resources/webhook),
then add its complete URL only to the ignored host `.env`:

```dotenv
MINXIONGHYDROCAST_DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/WEBHOOK_ID/WEBHOOK_TOKEN
```

Re-run the idempotent installer to copy the secret and restart the receiver:

```bash
deploy/single-host/install-user-host.sh --env-file .env
```

The backend accepts only official HTTPS Discord webhook URLs, requests Discord confirmation with
`wait=true`, disables all role/user/everyone mentions, keeps messages within Discord embed limits,
and retries rate limits or server failures within the Alertmanager request timeout. A failed
delivery returns HTTP 502 so Alertmanager can retry. Delivery results contain only a message ID or
redacted error code and are fsynced separately at:

```text
/mnt/8tb_hdd/ryo/minxiong-hydrocast/notifications/discord-deliveries.jsonl
```

Treat the URL as a password and rotate it in Discord if it is exposed. It must not be committed or
placed in a command-line argument.

Run a local end-to-end drill:

```bash
~/.local/share/minxiong-hydrocast/bin/amtool \
  --alertmanager.url=http://127.0.0.1:9093 \
  alert add MinxiongHydroCastDrill severity=warning service=minxiong-hydrocast \
  --annotation=summary='MinxiongHydroCast notification drill'
sleep 12
tail -n 1 ~/.local/share/minxiong-hydrocast/notifications/alerts.jsonl
test ! -f ~/.local/share/minxiong-hydrocast/notifications/discord-deliveries.jsonl || \
  tail -n 1 ~/.local/share/minxiong-hydrocast/notifications/discord-deliveries.jsonl
~/.local/share/minxiong-hydrocast/bin/amtool \
  --alertmanager.url=http://127.0.0.1:9093 \
  alert add MinxiongHydroCastDrill severity=warning service=minxiong-hydrocast \
  --end="$(date --iso-8601=seconds)"
```

## Backup and restore drill

The daily timer creates a compressed archive beside a Pydantic-validated metadata sidecar. Backup
creation holds the collector lock and verifies every retained manifest and dataset checksum before
writing the archive. Restore rejects links, path traversal, checksum mismatches, existing targets,
and snapshots that fail integrity verification.

Create, verify, and restore a fresh backup:

```bash
systemctl --user start minxiong-hydrocast-backup.service
archive="$(find ~/.local/share/minxiong-hydrocast/backups -name '*.tar.gz' -printf '%T@ %p\n' \
  | sort -n | tail -n 1 | cut -d' ' -f2-)"
~/.local/share/minxiong-hydrocast/venv/bin/minxiong-hydrocast-backup \
  verify --archive "$archive"
target="$HOME/.local/share/minxiong-hydrocast/restore_drills/$(date +%Y%m%dT%H%M%S)"
~/.local/share/minxiong-hydrocast/venv/bin/minxiong-hydrocast-backup \
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
systemctl --user --no-pager status minxiong-hydrocast-runner.service
```

The installer obtains a short-lived registration token through the authenticated `gh` session,
verifies the official runner asset digest, and applies the `minxiong-hydrocast` label. The workflow
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

Public exposure, automated risk notification, and forecast promotion remain blocked while this
gate is accumulating or any operational drill is unresolved. Internal code and documentation may
merge independently when their own review and CI checks pass.
