#!/usr/bin/env bash
set -euo pipefail

PROMETHEUS_VERSION="3.13.1"
ALERTMANAGER_VERSION="0.33.1"
RUNTIME_ROOT="${1:-$HOME/.local/share/floodcast-minxiong}"
BIN_DIR="$RUNTIME_ROOT/bin"

if [[ "$(uname -s)" != "Linux" || "$(uname -m)" != "x86_64" ]]; then
  echo "[ERROR] This installer supports Linux x86_64 only" >&2
  exit 1
fi

install_release() {
  local project="$1"
  local version="$2"
  local binary="$3"
  local asset="${project}-${version}.linux-amd64.tar.gz"
  local base="https://github.com/prometheus/${project}/releases/download/v${version}"
  local temporary
  temporary="$(mktemp -d)"
  trap 'rm -rf "$temporary"' RETURN

  curl --fail --location --retry 3 --silent --show-error \
    --output "$temporary/$asset" "$base/$asset"
  curl --fail --location --retry 3 --silent --show-error \
    --output "$temporary/sha256sums.txt" "$base/sha256sums.txt"
  grep "  ${asset}$" "$temporary/sha256sums.txt" > "$temporary/asset.sha256"
  (
    cd "$temporary"
    sha256sum --check asset.sha256
  )
  tar -xzf "$temporary/$asset" -C "$temporary"
  install -m 0755 "$temporary/${project}-${version}.linux-amd64/$binary" "$BIN_DIR/$binary"
  if [[ "$project" == "prometheus" ]]; then
    install -m 0755 "$temporary/${project}-${version}.linux-amd64/promtool" "$BIN_DIR/promtool"
  else
    install -m 0755 "$temporary/${project}-${version}.linux-amd64/amtool" "$BIN_DIR/amtool"
  fi
  rm -rf "$temporary"
  trap - RETURN
}

mkdir -p "$BIN_DIR"
install_release prometheus "$PROMETHEUS_VERSION" prometheus
install_release alertmanager "$ALERTMANAGER_VERSION" alertmanager

"$BIN_DIR/prometheus" --version
"$BIN_DIR/alertmanager" --version
echo "[OK] Monitoring binaries installed under $BIN_DIR"
