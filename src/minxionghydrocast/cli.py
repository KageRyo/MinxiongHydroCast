"""Single, grouped command-line interface for MinxiongHydroCast."""

from __future__ import annotations

import sys
from importlib import import_module
from typing import Sequence

CommandPath = tuple[str, ...]

# The public CLI is intentionally organized by workflow. Python modules remain independently
# runnable for maintainers, but the installed wheel exposes only the ``mhc`` executable.
COMMANDS: dict[CommandPath, str] = {
    ("collect",): "minxionghydrocast.operations.collector:main",
    ("serve",): "minxionghydrocast.operations.api:main",
    ("demo",): "minxionghydrocast.pipelines.demo:main",
    ("dataset", "build"): "minxionghydrocast.pipelines.dataset_build:main",
    ("dataset", "qpe-gauge-validate"): (
        "minxionghydrocast.pipelines.qpe_gauge_validation:main"
    ),
    ("dataset", "radar-event-summary"): (
        "minxionghydrocast.pipelines.radar_event_summary:main"
    ),
    ("dataset", "radar-source-check"): "minxionghydrocast.ingestion.radar_sources:main",
    ("dataset", "radar-tensor-convert"): (
        "minxionghydrocast.pipelines.radar_tensor_conversion:main"
    ),
    ("dataset", "split-check"): "minxionghydrocast.pipelines.event_split_check:main",
    ("data", "relocate-root"): (
        "minxionghydrocast.operations.data_root_relocation:main"
    ),
    ("event", "discover"): "minxionghydrocast.pipelines.event_discovery:main",
    ("event", "queue"): "minxionghydrocast.pipelines.event_review_queue:main",
    ("event", "review"): "minxionghydrocast.pipelines.event_review:main",
    ("labels", "audit"): "minxionghydrocast.validation.flood_labels:main",
    ("model", "evaluate"): "minxionghydrocast.pipelines.baseline_evaluation:main",
    ("model", "evaluate-tensor"): (
        "minxionghydrocast.pipelines.tensor_baseline_evaluation:main"
    ),
    ("model", "evaluate-optical-flow"): (
        "minxionghydrocast.pipelines.optical_flow_evaluation:main"
    ),
    ("model", "optical-flow-report"): (
        "minxionghydrocast.pipelines.optical_flow_report:main"
    ),
    ("model", "evaluate-torch"): (
        "minxionghydrocast.pipelines.torch_baseline_evaluation:main"
    ),
    ("model", "nowcastnet-smoke"): "minxionghydrocast.pipelines.nowcastnet_smoke:main",
    ("model", "train"): "minxionghydrocast.pipelines.torch_baseline_training:main",
    ("operations", "alert-receiver"): (
        "minxionghydrocast.operations.alert_receiver:main"
    ),
    ("operations", "backup"): "minxionghydrocast.operations.backup:main",
    ("operations", "gap-incidents"): "minxionghydrocast.operations.gap_incidents:main",
    ("operations", "shadow"): "minxionghydrocast.operations.shadow:main",
    ("source", "cwa-download"): "minxionghydrocast.ingestion.cwa_file_api:main",
    ("source", "cwa-event-plan"): (
        "minxionghydrocast.ingestion.cwa_event_collector:main"
    ),
    ("source", "cwa-grid-inspect"): "minxionghydrocast.ingestion.cwa_grid:main",
    ("source", "cwa-history-data-download"): (
        "minxionghydrocast.ingestion.cwa_history_data:main"
    ),
    ("source", "cwa-history-list"): "minxionghydrocast.ingestion.cwa_history:main",
    ("source", "cwa-rain-smoke"): "minxionghydrocast.ingestion.cwa_rainfall_api:main",
    ("source", "hydrology"): "minxionghydrocast.ingestion.hydrological_data:main",
    ("source", "rainfall-alerts"): "minxionghydrocast.ingestion.rainfall_alerts:main",
    ("source", "shelters"): "minxionghydrocast.ingestion.shelters:main",
    ("source", "wra-alert-smoke"): (
        "minxionghydrocast.ingestion.wra_rainfall_alert_api:main"
    ),
    ("source", "wra-flood-smoke"): (
        "minxionghydrocast.ingestion.wra_flood_sensor_api:main"
    ),
    ("spatial", "locations"): "minxionghydrocast.pipelines.location_reference:main",
}

# Keep source-checkout workflows compatible for one transition period. These are command aliases,
# not additional installed executables.
ALIASES: dict[CommandPath, CommandPath] = {
    ("operations",): ("collect",),
    ("backup",): ("operations", "backup"),
    ("dataset-build",): ("dataset", "build"),
    ("event-discover",): ("event", "discover"),
    ("event-review",): ("event", "review"),
    ("event-review-queue",): ("event", "queue"),
    ("event-split-check",): ("dataset", "split-check"),
    ("evaluate-baselines",): ("model", "evaluate"),
    ("nowcastnet-smoke",): ("model", "nowcastnet-smoke"),
    ("qpe-gauge-validate",): ("dataset", "qpe-gauge-validate"),
    ("radar-event-summary",): ("dataset", "radar-event-summary"),
    ("radar-source-check",): ("dataset", "radar-source-check"),
    ("radar-tensor-convert",): ("dataset", "radar-tensor-convert"),
    ("shadow-gap-incidents",): ("operations", "gap-incidents"),
    ("shadow-report",): ("operations", "shadow"),
    ("tensor-baseline-evaluate",): ("model", "evaluate-tensor"),
    ("torch-baseline-evaluate",): ("model", "evaluate-torch"),
    ("train-torch-baseline",): ("model", "train"),
}


def _groups() -> list[str]:
    return sorted({path[0] for path in COMMANDS if len(path) > 1})


def _print_help(group: str | None = None) -> None:
    if group is not None:
        print(f"usage: mhc {group} <command> [args]")
        print()
        print(f"{group} commands:")
        for path in sorted(path for path in COMMANDS if path[0] == group):
            print(f"  {path[1]}")
        print()
        print(f"Run 'mhc {group} <command> --help' for command-specific options.")
        return

    print("usage: mhc <command> [args]")
    print()
    print("Official-source hydrometeorological data and model workflows.")
    print()
    print("commands:")
    for path in sorted(path for path in COMMANDS if len(path) == 1):
        print(f"  {path[0]}")
    for group_name in _groups():
        print(f"  {group_name} <command>")
    print()
    print("examples:")
    print("  mhc collect --region minxiong --mode demo --once")
    print("  mhc serve --host 127.0.0.1 --port 8080")
    print("  mhc dataset build --help")
    print("  mhc data relocate-root --help")
    print("  mhc event review --help")
    print("  mhc model evaluate --help")
    print("  mhc operations backup --help")


def _resolve(arguments: list[str]) -> tuple[CommandPath, int] | None:
    if len(arguments) >= 2:
        nested = (arguments[0], arguments[1])
        if nested in COMMANDS:
            return nested, 2
    direct = (arguments[0],)
    if direct in COMMANDS:
        return direct, 1
    alias = ALIASES.get(direct)
    if alias is not None:
        return alias, 1
    return None


def main(argv: Sequence[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] in {"-h", "--help"}:
        _print_help()
        return
    if (
        arguments[0] in _groups()
        and (len(arguments) == 1 or arguments[1] in {"-h", "--help"})
    ):
        _print_help(arguments[0])
        return

    resolved = _resolve(arguments)
    if resolved is None:
        requested = " ".join(arguments[:2] if arguments[0] in _groups() else arguments[:1])
        print(f"mhc: unknown command: {requested}", file=sys.stderr)
        print("Run 'mhc --help' to list available commands.", file=sys.stderr)
        raise SystemExit(2)

    command_path, consumed = resolved
    target = COMMANDS[command_path]
    module_name, function_name = target.split(":", maxsplit=1)
    command_main = getattr(import_module(module_name), function_name)
    original_argv = sys.argv
    try:
        command_name = " ".join(arguments[:consumed])
        sys.argv = [f"mhc {command_name}", *arguments[consumed:]]
        command_main()
    finally:
        sys.argv = original_argv
