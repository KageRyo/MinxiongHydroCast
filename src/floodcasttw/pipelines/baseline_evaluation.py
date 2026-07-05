"""Run baseline model evaluations."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.evaluation import evaluate_all, write_evaluation_result

PIPELINE_NAME = "baseline_evaluation"


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate FloodCastTW baseline models.")
    parser.add_argument(
        "--events",
        type=Path,
        default=Path("data/samples/flood_risk_events.csv"),
        help="CSV containing threshold event examples.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/baseline_evaluation.json"),
    )
    parser.add_argument("--horizon", type=int, default=3)
    parser.add_argument("--event-threshold-mm", type=float, default=10.0)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    result = evaluate_all(
        event_path=args.events,
        horizon=args.horizon,
        event_threshold_mm=args.event_threshold_mm,
    )
    write_evaluation_result(result, args.output)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={"events": str(args.events)},
        outputs={"evaluation": str(args.output)},
        row_counts={"events": result["flood_risk"]["event_count"]},
        metrics={
            "nowcasting_rmse_mm": result["nowcasting"]["rmse_mm"],
            "flood_risk_csi": result["flood_risk"]["event_metrics"]["csi"],
        },
        metadata={
            "horizon": args.horizon,
            "event_threshold_mm": args.event_threshold_mm,
        },
    )
    record_run(
        summary_output=args.summary_output,
        log_output=args.log_output,
        summary=summary,
    )
    print(f"[OK] Wrote baseline evaluation to {args.output}")


if __name__ == "__main__":
    main()
