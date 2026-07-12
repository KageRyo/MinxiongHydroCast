#!/usr/bin/env bash
set -euo pipefail

RUNNER_VERSION="2.335.1"
REPOSITORY="${1:-KageRyo/FloodCastMinxiong}"
RUNTIME_ROOT="${2:-$HOME/.local/share/floodcast-minxiong}"
RUNNER_ROOT="$RUNTIME_ROOT/actions-runner"
ASSET="actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz"

if [[ "$(id -u)" == "0" ]]; then
  echo "[ERROR] Run the Actions runner installer as the service user, not root" >&2
  exit 1
fi
if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "[ERROR] This installer supports Linux x86_64 only" >&2
  exit 1
fi
command -v gh >/dev/null || {
  echo "[ERROR] gh is required and must already be authenticated" >&2
  exit 1
}

mkdir -p "$RUNNER_ROOT"
if [[ -f "$RUNNER_ROOT/.runner" ]]; then
  echo "[OK] Actions runner is already configured at $RUNNER_ROOT"
  exit 0
fi
if [[ -n "$(find "$RUNNER_ROOT" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "[ERROR] Refusing to install into non-empty runner directory: $RUNNER_ROOT" >&2
  exit 1
fi

temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
digest="$(gh release view "v$RUNNER_VERSION" --repo actions/runner --json assets \
  --jq ".assets[] | select(.name == \"$ASSET\") | .digest")"
expected_sha="${digest#sha256:}"
if [[ ! "$expected_sha" =~ ^[0-9a-fA-F]{64}$ ]]; then
  echo "[ERROR] GitHub did not return a valid SHA-256 digest for $ASSET" >&2
  exit 1
fi
gh release download "v$RUNNER_VERSION" --repo actions/runner \
  --pattern "$ASSET" --dir "$temporary"
printf '%s  %s\n' "$expected_sha" "$temporary/$ASSET" | sha256sum --check
tar -xzf "$temporary/$ASSET" -C "$RUNNER_ROOT"

registration_token="$(gh api --method POST \
  "repos/$REPOSITORY/actions/runners/registration-token" --jq .token)"
runner_name="$(hostname)-floodcast-minxiong"
(
  cd "$RUNNER_ROOT"
  ./config.sh --unattended --replace \
    --url "https://github.com/$REPOSITORY" \
    --token "$registration_token" \
    --name "$runner_name" \
    --labels floodcast-minxiong \
    --work _work
)
unset registration_token

systemctl --user daemon-reload
systemctl --user enable --now floodcast-minxiong-runner.service
echo "[OK] Actions runner $runner_name installed and started"
