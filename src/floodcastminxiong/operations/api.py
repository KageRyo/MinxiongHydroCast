"""Read-only JSON API and operator view for operational snapshots."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from floodcastminxiong.operations.collector import DEFAULT_STORE
from floodcastminxiong.operations.health import aggregate_health, refresh_dataset_health
from floodcastminxiong.operations.snapshot_store import SnapshotStore, SnapshotStoreError

TAIPEI_TZ = ZoneInfo("Asia/Taipei")

DATASET_ROUTES = {
    "/api/v1/official-alerts/rainfall": "rainfall_alerts",
    "/api/v1/observations/rain-gauges": "rain_gauges",
    "/api/v1/observations/flood-sensors": "flood_sensors",
}

PRODUCT_NOTICES = {
    "demo_fixture": (
        "Synthetic fixture for installation and contract tests. Not live or official data."
    ),
    "official_alert": (
        "Source product collected from Taiwan WRA. FloodCastMinxiong does not issue or replace "
        "official warnings."
    ),
    "official_observation": (
        "Observation collected from Taiwan WRA and validated by FloodCastMinxiong."
    ),
    "experimental_forecast": (
        "Experimental model output. Not an official warning and not for automated public action."
    ),
}


def status_payload(
    store: SnapshotStore,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(TAIPEI_TZ)
    try:
        latest = store.read_latest()
        attempt = store.read_latest_attempt()
    except SnapshotStoreError as exc:
        return {
            "state": "storage_error",
            "ready": False,
            "checked_at": now.isoformat(timespec="seconds"),
            "failure_reason": str(exc),
            "latest_snapshot": None,
            "latest_attempt": None,
            "datasets": {},
        }
    if latest is None:
        state = "collector_error" if attempt and attempt.get("status") == "error" else "uninitialized"
        return {
            "state": state,
            "ready": False,
            "checked_at": now.isoformat(timespec="seconds"),
            "latest_snapshot": None,
            "latest_attempt": attempt,
            "datasets": {},
        }

    integrity_errors = store.verify_snapshot(latest)
    if integrity_errors:
        return {
            "state": "storage_error",
            "ready": False,
            "checked_at": now.isoformat(timespec="seconds"),
            "failure_reason": "; ".join(integrity_errors),
            "latest_snapshot": {
                "snapshot_id": latest["snapshot_id"],
                "mode": latest["mode"],
                "completed_at": latest["completed_at"],
            },
            "latest_attempt": {
                "snapshot_id": attempt["snapshot_id"],
                "status": attempt["status"],
                "completed_at": attempt["completed_at"],
                "failure_reason": attempt.get("failure_reason", ""),
            }
            if attempt
            else None,
            "datasets": latest.get("datasets", {}),
        }

    refreshed_datasets: dict[str, Any] = {}
    for name, details in latest.get("datasets", {}).items():
        refreshed = dict(details)
        refreshed["health"] = refresh_dataset_health(
            dict(details.get("health", {})),
            mode=str(latest.get("mode", "")),
            now=now,
        )
        refreshed_datasets[name] = refreshed
    health = aggregate_health(refreshed_datasets, mode=str(latest.get("mode", "")))
    if (
        attempt
        and attempt.get("status") == "error"
        and attempt.get("snapshot_id") != latest.get("snapshot_id")
    ):
        health["state"] = "collector_error"
        health["ready"] = False

    return {
        "state": health["state"],
        "ready": health["ready"],
        "checked_at": now.isoformat(timespec="seconds"),
        "latest_snapshot": {
            "snapshot_id": latest["snapshot_id"],
            "mode": latest["mode"],
            "completed_at": latest["completed_at"],
            "health": health,
        },
        "latest_attempt": {
            "snapshot_id": attempt["snapshot_id"],
            "status": attempt["status"],
            "completed_at": attempt["completed_at"],
            "failure_reason": attempt.get("failure_reason", ""),
        }
        if attempt
        else None,
        "datasets": refreshed_datasets,
    }


def dataset_payload(
    store: SnapshotStore,
    name: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    latest = store.read_latest()
    if latest is None:
        raise KeyError(name)
    details = latest.get("datasets", {}).get(name)
    if not isinstance(details, dict):
        raise KeyError(name)
    health = refresh_dataset_health(
        dict(details.get("health", {})),
        mode=str(latest.get("mode", "")),
        now=now or datetime.now(TAIPEI_TZ),
    )
    product_type = str(details["product_type"])
    return {
        "schema_version": 1,
        "snapshot_id": latest["snapshot_id"],
        "generated_at": latest["completed_at"],
        "mode": latest["mode"],
        "dataset": name,
        "product_type": product_type,
        "notice": PRODUCT_NOTICES[product_type],
        "health": health,
        "row_count": details["row_count"],
        "records": store.read_dataset(latest, name),
    }


def forecast_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "available": False,
        "product_type": "experimental_forecast",
        "notice": PRODUCT_NOTICES["experimental_forecast"],
        "reason": "No forecast has passed the model and shadow-deployment gates.",
        "records": [],
    }


def shadow_payload(store: SnapshotStore) -> dict[str, Any]:
    try:
        report = store.read_report("shadow_report.json")
    except SnapshotStoreError as exc:
        return {
            "state": "storage_error",
            "shadow_gate_passed": False,
            "notification_allowed": False,
            "notification_blockers": [str(exc)],
        }
    if report is None:
        return {
            "state": "not_evaluated",
            "shadow_gate_passed": False,
            "notification_allowed": False,
            "notification_blockers": [
                "shadow report has not been generated",
                "notification delivery is not implemented and local model-label gates "
                "are not satisfied",
            ],
        }
    return {
        "state": "passed" if report.get("shadow_gate_passed") else "blocked",
        **report,
    }


def metrics_payload(status: dict[str, Any]) -> str:
    ready = 1 if status["ready"] else 0
    attempt = status.get("latest_attempt") or {}
    attempt_ok = 1 if attempt.get("status") == "ok" else 0
    lines = [
        "# HELP floodcastminxiong_ready Whether operational data passes readiness gates.",
        "# TYPE floodcastminxiong_ready gauge",
        f"floodcastminxiong_ready {ready}",
        "# HELP floodcastminxiong_last_attempt_success Whether the last collection succeeded.",
        "# TYPE floodcastminxiong_last_attempt_success gauge",
        f"floodcastminxiong_last_attempt_success {attempt_ok}",
        "# HELP floodcastminxiong_dataset_age_minutes Age of the latest dataset observation.",
        "# TYPE floodcastminxiong_dataset_age_minutes gauge",
    ]
    for name, details in sorted(status.get("datasets", {}).items()):
        health = details.get("health", {})
        age = health.get("age_minutes")
        if age is not None:
            lines.append(f'floodcastminxiong_dataset_age_minutes{{dataset="{name}"}} {age}')
    lines.extend(
        [
            "# HELP floodcastminxiong_dataset_state Current dataset health state.",
            "# TYPE floodcastminxiong_dataset_state gauge",
        ]
    )
    for name, details in sorted(status.get("datasets", {}).items()):
        state = str(details.get("health", {}).get("state", "unknown"))
        lines.append(
            f'floodcastminxiong_dataset_state{{dataset="{name}",state="{state}"}} 1'
        )
    return "\n".join(lines) + "\n"


def shadow_metrics_payload(report: dict[str, Any]) -> str:
    passed = 1 if report.get("shadow_gate_passed") else 0
    allowed = 1 if report.get("notification_allowed") else 0
    return (
        "# HELP floodcastminxiong_shadow_gate_passed Whether shadow criteria passed.\n"
        "# TYPE floodcastminxiong_shadow_gate_passed gauge\n"
        f"floodcastminxiong_shadow_gate_passed {passed}\n"
        "# HELP floodcastminxiong_notification_allowed Whether notifications may be enabled.\n"
        "# TYPE floodcastminxiong_notification_allowed gauge\n"
        f"floodcastminxiong_notification_allowed {allowed}\n"
    )


OPERATOR_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FloodCastMinxiong Operations</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, sans-serif;
      color: #202428;
      background: #f4f6f7;
    }
    * { box-sizing: border-box; }
    body { margin: 0; min-width: 320px; }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      color: #fff;
      background: #202428;
      border-bottom: 4px solid #2f7d57;
    }
    h1, h2 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 20px; }
    h2 { font-size: 15px; }
    button {
      min-height: 36px;
      padding: 0 14px;
      color: #202428;
      background: #fff;
      border: 1px solid #b8c0c5;
      border-radius: 4px;
      font: inherit;
      cursor: pointer;
    }
    main { max-width: 1440px; margin: 0 auto; padding: 20px 24px 40px; }
    .status {
      display: grid;
      grid-template-columns: minmax(140px, 0.6fr) repeat(4, minmax(150px, 1fr));
      margin-bottom: 22px;
      background: #fff;
      border: 1px solid #d4dadd;
      border-radius: 6px;
      overflow: hidden;
    }
    .status > div { min-height: 78px; padding: 14px 16px; border-right: 1px solid #e2e6e8; }
    .status > div:last-child { border-right: 0; }
    .label { margin-bottom: 6px; color: #667078; font-size: 12px; text-transform: uppercase; }
    .value { font-weight: 650; overflow-wrap: anywhere; }
    .healthy { color: #146c43; }
    .demo, .stale { color: #9b5c00; }
    .unhealthy, .collector_error, .storage_error, .invalid, .unavailable { color: #b42318; }
    section { margin-top: 22px; background: #fff; border-top: 3px solid #4a6572; }
    section.experimental { border-top-color: #b96d00; }
    .section-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border: 1px solid #d4dadd;
      border-top: 0;
    }
    .section-head span { color: #667078; font-size: 12px; }
    .table-wrap { overflow-x: auto; border: 1px solid #d4dadd; border-top: 0; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid #e6eaec; }
    th { color: #4f5960; background: #f7f8f9; font-weight: 650; white-space: nowrap; }
    tr:last-child td { border-bottom: 0; }
    .empty { padding: 18px 14px; color: #667078; }
    @media (max-width: 800px) {
      header { align-items: flex-start; padding: 16px; }
      main { padding: 16px; }
      .status { grid-template-columns: 1fr 1fr; }
      .status > div:nth-child(2) { border-right: 0; }
      .status > div { border-bottom: 1px solid #e2e6e8; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>FloodCastMinxiong Operations</h1>
      <div id="checked" style="margin-top:4px;color:#c7d0d5;font-size:12px">Loading</div>
    </div>
    <button id="refresh" type="button">Refresh</button>
  </header>
  <main>
    <div class="status">
      <div><div class="label">Readiness</div><div class="value" id="state">Loading</div></div>
      <div><div class="label">Snapshot</div><div class="value" id="snapshot">-</div></div>
      <div><div class="label">Mode</div><div class="value" id="mode">-</div></div>
      <div><div class="label">Last attempt</div><div class="value" id="attempt">-</div></div>
      <div><div class="label">Shadow gate</div><div class="value" id="shadow">-</div></div>
    </div>
    <section>
      <div class="section-head"><h2>WRA Rainfall Alerts</h2><span id="alerts-type">Loading</span></div>
      <div class="table-wrap" id="alerts"></div>
    </section>
    <section>
      <div class="section-head"><h2>Rain Gauges</h2><span id="gauges-type">Loading</span></div>
      <div class="table-wrap" id="gauges"></div>
    </section>
    <section>
      <div class="section-head"><h2>Flood Sensors</h2><span id="sensors-type">Loading</span></div>
      <div class="table-wrap" id="sensors"></div>
    </section>
    <section class="experimental">
      <div class="section-head"><h2>Experimental Forecast</h2><span>Not an official warning</span></div>
      <div class="empty" id="forecast">Loading</div>
    </section>
  </main>
  <script>
    const endpoints = {
      alerts: "/api/v1/official-alerts/rainfall",
      gauges: "/api/v1/observations/rain-gauges",
      sensors: "/api/v1/observations/flood-sensors"
    };
    const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, char => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    })[char]);
    function renderTable(target, payload) {
      const rows = payload.records || [];
      if (!rows.length) {
        target.innerHTML = '<div class="empty">No records available</div>';
        return;
      }
      const fields = Object.keys(rows[0]);
      target.innerHTML = "<table><thead><tr>" +
        fields.map(field => "<th>" + escapeHtml(field) + "</th>").join("") +
        "</tr></thead><tbody>" +
        rows.map(row => "<tr>" + fields.map(field =>
          "<td>" + escapeHtml(row[field]) + "</td>").join("") + "</tr>").join("") +
        "</tbody></table>";
    }
    async function getJson(path) {
      const response = await fetch(path, {cache: "no-store"});
      if (!response.ok) throw new Error(path + " returned " + response.status);
      return response.json();
    }
    async function refresh() {
      const status = await getJson("/api/v1/status");
      const state = document.getElementById("state");
      state.textContent = status.state;
      state.className = "value " + status.state;
      document.getElementById("checked").textContent = "Checked " + status.checked_at;
      const latest = status.latest_snapshot;
      document.getElementById("snapshot").textContent = latest?.snapshot_id || "-";
      document.getElementById("mode").textContent = latest?.mode || "-";
      const attempt = status.latest_attempt;
      document.getElementById("attempt").textContent =
        attempt ? attempt.status + " at " + attempt.completed_at : "-";
      const shadow = await getJson("/api/v1/shadow-readiness");
      const shadowState = document.getElementById("shadow");
      shadowState.textContent = shadow.state;
      shadowState.className = "value " +
        (shadow.shadow_gate_passed ? "healthy" : "unhealthy");
      for (const [target, path] of Object.entries(endpoints)) {
        try {
          const payload = await getJson(path);
          document.getElementById(target + "-type").textContent =
            "Source classification: " + payload.product_type;
          renderTable(document.getElementById(target), payload);
        }
        catch (error) { document.getElementById(target).innerHTML =
          '<div class="empty">' + escapeHtml(error.message) + "</div>"; }
      }
      const forecast = await getJson("/api/v1/experimental-forecasts");
      document.getElementById("forecast").textContent = forecast.reason;
    }
    document.getElementById("refresh").addEventListener("click", refresh);
    refresh().catch(error => {
      const state = document.getElementById("state");
      state.textContent = error.message;
      state.className = "value unhealthy";
    });
    setInterval(refresh, 30000);
  </script>
</body>
</html>
"""


def handler_factory(store: SnapshotStore) -> type[BaseHTTPRequestHandler]:
    class OperationsHandler(BaseHTTPRequestHandler):
        server_version = "FloodCastMinxiong/0.1"

        def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                body = OPERATOR_HTML.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()
                self.wfile.write(body)
                return
            if path == "/healthz":
                self._json({"status": "ok"})
                return
            if path == "/metrics":
                body = (
                    metrics_payload(status_payload(store))
                    + shadow_metrics_payload(shadow_payload(store))
                ).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if path in {"/readyz", "/api/v1/status"}:
                status = status_payload(store)
                http_status = (
                    HTTPStatus.OK
                    if path == "/api/v1/status" or status["ready"]
                    else HTTPStatus.SERVICE_UNAVAILABLE
                )
                self._json(status, http_status)
                return
            if path in DATASET_ROUTES:
                try:
                    payload = dataset_payload(store, DATASET_ROUTES[path])
                except (KeyError, SnapshotStoreError):
                    self._json(
                        {"error": "dataset unavailable", "path": path},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return
                self._json(payload)
                return
            if path == "/api/v1/experimental-forecasts":
                self._json(forecast_payload())
                return
            if path == "/api/v1/shadow-readiness":
                self._json(shadow_payload(store))
                return
            self._json({"error": "not found", "path": path}, HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            print(f"[HTTP] {self.address_string()} {format % args}")

    return OperationsHandler


def build_server(
    store: SnapshotStore,
    *,
    host: str,
    port: int,
) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), handler_factory(store))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Serve the FloodCastMinxiong observation API and operator view.",
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = build_server(SnapshotStore(args.store), host=args.host, port=args.port)
    address, port = server.server_address[:2]
    print(f"[OK] Serving FloodCastMinxiong operations at http://{address}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[INFO] Server stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
