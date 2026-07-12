#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 --env-file PATH [--durable-root PATH] [--python PATH]" >&2
}

REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DURABLE_ROOT="/mnt/8tb_hdd/ryo/floodcast-minxiong"
ENV_FILE=""
PYTHON_BIN="python3"
RUNTIME_LINK="$HOME/.local/share/floodcast-minxiong"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --durable-root)
      DURABLE_ROOT="$2"
      shift 2
      ;;
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [[ "$(id -u)" == "0" ]]; then
  echo "[ERROR] Run this installer as the service user, not root" >&2
  exit 1
fi
if ! git -C "$REPOSITORY_ROOT" diff --quiet || \
  ! git -C "$REPOSITORY_ROOT" diff --cached --quiet || \
  [[ -n "$(git -C "$REPOSITORY_ROOT" ls-files --others --exclude-standard)" ]]; then
  echo "[ERROR] Refusing to deploy an uncommitted repository state" >&2
  exit 1
fi
if [[ -z "$ENV_FILE" || ! -f "$ENV_FILE" ]]; then
  usage
  exit 2
fi
if ! grep -Eq '^[[:space:]]*CWA_API_KEY=.+$' "$ENV_FILE"; then
  echo "[ERROR] CWA_API_KEY is missing from the environment file" >&2
  exit 1
fi
if ! grep -Eq '^[[:space:]]*WRA_API_KEY=.+$' "$ENV_FILE"; then
  echo "[ERROR] WRA_API_KEY is missing from the environment file" >&2
  exit 1
fi

DURABLE_ROOT="$(realpath -m "$DURABLE_ROOT")"
mkdir -p "$DURABLE_ROOT"
chmod 0700 "$DURABLE_ROOT"
for directory in alertmanager backups bin config/prometheus debug notifications operations \
  prometheus restore_drills run_summaries; do
  mkdir -p "$DURABLE_ROOT/$directory"
done

mkdir -p "$(dirname "$RUNTIME_LINK")"
if [[ -L "$RUNTIME_LINK" ]]; then
  current_target="$(realpath "$RUNTIME_LINK")"
  if [[ "$current_target" != "$DURABLE_ROOT" ]]; then
    echo "[ERROR] Runtime link points to $current_target, expected $DURABLE_ROOT" >&2
    exit 1
  fi
elif [[ -e "$RUNTIME_LINK" ]]; then
  echo "[ERROR] Refusing to replace existing runtime path: $RUNTIME_LINK" >&2
  exit 1
else
  ln -s "$DURABLE_ROOT" "$RUNTIME_LINK"
fi

if [[ ! -x "$DURABLE_ROOT/venv/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$DURABLE_ROOT/venv"
fi
"$DURABLE_ROOT/venv/bin/python" -m pip install --upgrade "$REPOSITORY_ROOT"
"$DURABLE_ROOT/venv/bin/python" -m pip freeze \
  > "$DURABLE_ROOT/config/installed-packages.txt"
git -C "$REPOSITORY_ROOT" rev-parse HEAD \
  > "$DURABLE_ROOT/config/installed-revision.txt"

mkdir -p "$HOME/.config/floodcast-minxiong" "$HOME/.config/systemd/user"
install -m 0600 "$ENV_FILE" "$HOME/.config/floodcast-minxiong/env"
install -m 0644 "$REPOSITORY_ROOT"/deploy/prometheus/*.yml \
  "$DURABLE_ROOT/config/prometheus/"
install -m 0644 "$REPOSITORY_ROOT"/deploy/systemd-user/* \
  "$HOME/.config/systemd/user/"

if [[ ! -f "$DURABLE_ROOT/config/shadow_evidence.json" ]]; then
  install -m 0600 "$REPOSITORY_ROOT/data/samples/shadow_evidence.example.json" \
    "$DURABLE_ROOT/config/shadow_evidence.json"
fi

"$REPOSITORY_ROOT/deploy/single-host/install-monitoring.sh" "$DURABLE_ROOT"
"$DURABLE_ROOT/bin/promtool" check config \
  "$DURABLE_ROOT/config/prometheus/prometheus.yml"
"$DURABLE_ROOT/bin/promtool" check rules \
  "$DURABLE_ROOT/config/prometheus/floodcast.rules.yml"
"$DURABLE_ROOT/bin/amtool" check-config \
  "$DURABLE_ROOT/config/prometheus/alertmanager.yml"

systemctl --user daemon-reload
systemctl --user enable \
  floodcast-minxiong-alert-receiver.service \
  floodcast-minxiong-alertmanager.service \
  floodcast-minxiong-api.service \
  floodcast-minxiong-prometheus.service
systemctl --user restart \
  floodcast-minxiong-alert-receiver.service \
  floodcast-minxiong-alertmanager.service \
  floodcast-minxiong-api.service \
  floodcast-minxiong-prometheus.service
systemctl --user enable --now \
  floodcast-minxiong-collector.timer \
  floodcast-minxiong-backup.timer \
  floodcast-minxiong-shadow.timer
systemctl --user start floodcast-minxiong-collector.service
systemctl --user start floodcast-minxiong-shadow.service

echo "[OK] FloodCastMinxiong installed at $DURABLE_ROOT"
echo "[ACTION] Run 'sudo loginctl enable-linger $USER' once so user services survive logout"
