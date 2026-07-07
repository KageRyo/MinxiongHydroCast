"""Build CWA radar event collection plans from history indexes."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "cwa_event_plan"


@dataclass(frozen=True)
class CwaEventFrame:
    data_time: str
    url: str
    filename: str
    file_format: str

    def to_dict(self) -> dict[str, str]:
        return {
            "data_time": self.data_time,
            "url": self.url,
            "filename": self.filename,
            "file_format": self.file_format,
        }


@dataclass(frozen=True)
class CwaEventPlan:
    event_id: str
    data_id: str
    start_time: str
    end_time: str
    frame_count: int
    frames: tuple[CwaEventFrame, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "data_id": self.data_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "frame_count": self.frame_count,
            "frames": [frame.to_dict() for frame in self.frames],
        }


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_history_index(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("history index must be a JSON object")
    return payload


def build_event_plan(
    history_index: dict[str, Any],
    *,
    event_id: str,
    start_time: str,
    end_time: str,
    limit: int | None = None,
) -> CwaEventPlan:
    start = parse_iso_datetime(start_time)
    end = parse_iso_datetime(end_time)
    if end < start:
        raise ValueError("end_time must be greater than or equal to start_time")

    frames = []
    for item in history_index.get("files", []):
        if not isinstance(item, dict):
            continue
        data_time = str(item.get("data_time", ""))
        if not data_time:
            continue
        parsed = parse_iso_datetime(data_time)
        if start <= parsed <= end:
            frames.append(
                CwaEventFrame(
                    data_time=data_time,
                    url=str(item.get("url", "")),
                    filename=str(item.get("filename", "")),
                    file_format=str(item.get("file_format", "")),
                )
            )

    frames.sort(key=lambda frame: parse_iso_datetime(frame.data_time))
    if limit is not None:
        frames = frames[:limit]
    return CwaEventPlan(
        event_id=event_id,
        data_id=str(history_index.get("data_id", "")),
        start_time=start_time,
        end_time=end_time,
        frame_count=len(frames),
        frames=tuple(frames),
    )


def write_event_plan(path: Path, plan: CwaEventPlan) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a CWA radar event collection plan.")
    parser.add_argument("--history-index", type=Path, required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--start-time", required=True)
    parser.add_argument("--end-time", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("data/processed/cwa_event_plan.json"))
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    history_index = load_history_index(args.history_index)
    plan = build_event_plan(
        history_index,
        event_id=args.event_id,
        start_time=args.start_time,
        end_time=args.end_time,
        limit=args.limit,
    )
    write_event_plan(args.output, plan)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok" if plan.frames else "needs_review",
        failure_reason="" if plan.frames else "no frames selected",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"history_index": str(args.history_index)},
        outputs={"event_plan": str(args.output)},
        row_counts={"frames": plan.frame_count},
        metadata={
            "event_id": args.event_id,
            "data_id": plan.data_id,
            "start_time": args.start_time,
            "end_time": args.end_time,
            "limit": args.limit,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote CWA event plan to {args.output}")


if __name__ == "__main__":
    main()
