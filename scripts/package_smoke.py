#!/usr/bin/env python3
"""Smoke-test the installed wheel's CLI and synthetic observation service."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from importlib import metadata
from pathlib import Path

HOST = "127.0.0.1"
PORT = 18080
BASE_URL = f"http://{HOST}:{PORT}"


def request(path: str, *, expected_status: int = 200) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=2) as response:
            status = response.status
            body = response.read()
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read()
    if status != expected_status:
        raise RuntimeError(f"{path} returned {status}, expected {expected_status}: {body!r}")
    return status, body


def wait_until_healthy(process: subprocess.Popen[bytes]) -> None:
    for _attempt in range(50):
        if process.poll() is not None:
            raise RuntimeError(f"mhc serve exited early with status {process.returncode}")
        try:
            request("/healthz")
            return
        except (OSError, RuntimeError):
            time.sleep(0.1)
    raise RuntimeError("mhc serve did not become healthy")


def main() -> None:
    distribution = metadata.distribution("minxiong-hydrocast")
    expected_release_tag = os.environ.get("MHC_EXPECTED_RELEASE_TAG")
    if expected_release_tag is not None:
        package_tag = f"v{distribution.version}"
        if expected_release_tag != package_tag:
            raise RuntimeError(
                "GitHub release tag must match the wheel version: "
                f"{expected_release_tag} != {package_tag}"
            )
    console_scripts = sorted(
        entry_point.name
        for entry_point in distribution.entry_points
        if entry_point.group == "console_scripts"
    )
    if console_scripts != ["mhc"]:
        raise RuntimeError(f"wheel must expose only the mhc executable: {console_scripts}")

    subprocess.run(["mhc", "--help"], check=True)
    with tempfile.TemporaryDirectory(prefix="mhc-wheel-smoke-") as temporary:
        root = Path(temporary)
        store = root / "operations"
        subprocess.run(
            [
                "mhc",
                "collect",
                "--region",
                "minxiong",
                "--mode",
                "demo",
                "--once",
                "--store",
                str(store),
                "--summary-output",
                str(root / "summary.json"),
                "--log-output",
                str(root / "runs.jsonl"),
            ],
            check=True,
        )
        server = subprocess.Popen(
            [
                "mhc",
                "serve",
                "--host",
                HOST,
                "--port",
                str(PORT),
                "--store",
                str(store),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_until_healthy(server)
            _status, readiness_body = request("/readyz", expected_status=503)
            readiness = json.loads(readiness_body)
            if readiness["state"] != "demo" or readiness["ready"] is not False:
                raise RuntimeError(f"demo readiness must remain blocked: {readiness}")

            _status, status_body = request("/api/v1/status")
            status = json.loads(status_body)
            expected_datasets = {
                "rainfall_alerts",
                "rain_gauges",
                "flood_sensors",
                "region_features",
                "location_reference",
            }
            if set(status["datasets"]) != expected_datasets:
                raise RuntimeError(f"unexpected demo datasets: {status['datasets']}")

            _status, metrics = request("/metrics")
            if b"minxionghydrocast_ready 0" not in metrics:
                raise RuntimeError("Prometheus readiness metric is missing or unsafe")

            _status, forecast_body = request("/api/v1/experimental-forecasts")
            forecast = json.loads(forecast_body)
            if forecast["available"] is not False:
                raise RuntimeError("demo forecast gate must remain blocked")
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)


if __name__ == "__main__":
    main()
