"""Structured run summaries and JSON log helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
DEFAULT_RUN_LOG_PATH = Path("data/processed/run_logs.jsonl")


def now_taipei_iso() -> str:
    return datetime.now(TAIPEI_TZ).isoformat(timespec="seconds")


def start_run() -> tuple[str, float]:
    return now_taipei_iso(), time.perf_counter()


def default_run_summary_path(pipeline: str) -> Path:
    return Path("data/processed/run_summaries") / f"{pipeline}.json"


def build_run_summary(
    *,
    pipeline: str,
    status: str,
    started_at: str,
    start_timer: float,
    failure_reason: str = "",
    mode: str = "",
    inputs: dict[str, object] | None = None,
    outputs: dict[str, object] | None = None,
    row_counts: dict[str, object] | None = None,
    metrics: dict[str, object] | None = None,
    validation: dict[str, object] | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "pipeline": pipeline,
        "status": status,
        "failure_reason": failure_reason,
        "started_at": started_at,
        "completed_at": now_taipei_iso(),
        "duration_seconds": round(max(0.0, time.perf_counter() - start_timer), 3),
        "mode": mode,
        "inputs": inputs or {},
        "outputs": outputs or {},
        "row_counts": row_counts or {},
        "metrics": metrics or {},
        "validation": validation or {},
        "metadata": metadata or {},
    }


def write_run_summary(summary_output: Path | None, payload: dict[str, object]) -> None:
    if summary_output is None:
        return
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def append_json_log(log_output: Path | None, payload: dict[str, object]) -> None:
    if log_output is None:
        return
    log_output.parent.mkdir(parents=True, exist_ok=True)
    with log_output.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def run_log_event(summary: dict[str, object]) -> dict[str, object]:
    return {
        "timestamp": summary.get("completed_at", now_taipei_iso()),
        "level": "info" if summary.get("status") == "ok" else "error",
        "event": "run_completed",
        "pipeline": summary.get("pipeline", ""),
        "status": summary.get("status", ""),
        "failure_reason": summary.get("failure_reason", ""),
        "duration_seconds": summary.get("duration_seconds", 0),
    }


def record_run(
    *,
    summary_output: Path | None,
    log_output: Path | None,
    summary: dict[str, object],
) -> None:
    write_run_summary(summary_output, summary)
    append_json_log(log_output, run_log_event(summary))
