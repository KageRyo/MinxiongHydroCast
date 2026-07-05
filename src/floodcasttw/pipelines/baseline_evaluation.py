"""Run baseline model evaluations."""

from __future__ import annotations

import argparse
from pathlib import Path

from floodcasttw.models.evaluation import evaluate_all, write_evaluation_result


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
    args = parser.parse_args()

    result = evaluate_all(
        event_path=args.events,
        horizon=args.horizon,
        event_threshold_mm=args.event_threshold_mm,
    )
    write_evaluation_result(result, args.output)
    print(f"[OK] Wrote baseline evaluation to {args.output}")


if __name__ == "__main__":
    main()
