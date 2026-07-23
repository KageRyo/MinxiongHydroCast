"""Concise dispatcher for MinxiongHydroCast command-line tools."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Sequence

COMMANDS = {
    "alert-receiver": "minxionghydrocast.operations.alert_receiver:main",
    "backup": "minxionghydrocast.operations.backup:main",
    "cwa-download": "minxionghydrocast.ingestion.cwa_file_api:main",
    "cwa-event-plan": "minxionghydrocast.ingestion.cwa_event_collector:main",
    "cwa-grid-inspect": "minxionghydrocast.ingestion.cwa_grid:main",
    "cwa-history-data-download": "minxionghydrocast.ingestion.cwa_history_data:main",
    "cwa-history-list": "minxionghydrocast.ingestion.cwa_history:main",
    "cwa-rain-smoke": "minxionghydrocast.ingestion.cwa_rainfall_api:main",
    "dataset-build": "minxionghydrocast.pipelines.dataset_build:main",
    "demo": "minxionghydrocast.pipelines.demo:main",
    "evaluate-baselines": "minxionghydrocast.pipelines.baseline_evaluation:main",
    "event-discover": "minxionghydrocast.pipelines.event_discovery:main",
    "event-review": "minxionghydrocast.pipelines.event_review:main",
    "event-review-queue": "minxionghydrocast.pipelines.event_review_queue:main",
    "event-split-check": "minxionghydrocast.pipelines.event_split_check:main",
    "hydrology": "minxionghydrocast.ingestion.hydrological_data:main",
    "label-audit": "minxionghydrocast.validation.flood_labels:main",
    "locations": "minxionghydrocast.pipelines.location_reference:main",
    "nowcastnet-smoke": "minxionghydrocast.pipelines.nowcastnet_smoke:main",
    "operations": "minxionghydrocast.operations.collector:main",
    "qpe-gauge-validate": "minxionghydrocast.pipelines.qpe_gauge_validation:main",
    "radar-event-summary": "minxionghydrocast.pipelines.radar_event_summary:main",
    "radar-source-check": "minxionghydrocast.ingestion.radar_sources:main",
    "radar-tensor-convert": "minxionghydrocast.pipelines.radar_tensor_conversion:main",
    "rainfall-alerts": "minxionghydrocast.ingestion.rainfall_alerts:main",
    "serve": "minxionghydrocast.operations.api:main",
    "shadow-report": "minxionghydrocast.operations.shadow:main",
    "shelters": "minxionghydrocast.ingestion.shelters:main",
    "tensor-baseline-evaluate": "minxionghydrocast.pipelines.tensor_baseline_evaluation:main",
    "torch-baseline-evaluate": "minxionghydrocast.pipelines.torch_baseline_evaluation:main",
    "train-torch-baseline": "minxionghydrocast.pipelines.torch_baseline_training:main",
    "wra-alert-smoke": "minxionghydrocast.ingestion.wra_rainfall_alert_api:main",
    "wra-flood-smoke": "minxionghydrocast.ingestion.wra_flood_sensor_api:main",
}

ALIASES = {
    "collect": "operations",
    "shadow": "shadow-report",
}


def _print_help() -> None:
    print("usage: mhc <command> [args]")
    print()
    print("MinxiongHydroCast command dispatcher.")
    print()
    print("commands:")
    for command in sorted(COMMANDS):
        print(f"  {command}")
    print()
    print("aliases:")
    for alias, command in sorted(ALIASES.items()):
        print(f"  {alias} -> {command}")
    print()
    print("Run 'mhc <command> --help' for command-specific options.")


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        _print_help()
        return

    requested = arguments[0]
    command = ALIASES.get(requested, requested)
    target = COMMANDS.get(command)
    if target is None:
        print(f"mhc: unknown command: {requested}", file=sys.stderr)
        print("Run 'mhc --help' to list available commands.", file=sys.stderr)
        raise SystemExit(2)

    module_name, function_name = target.split(":", maxsplit=1)
    command_main = getattr(import_module(module_name), function_name)
    original_argv = sys.argv
    try:
        sys.argv = [f"mhc {requested}", *arguments[1:]]
        command_main()
    finally:
        sys.argv = original_argv
