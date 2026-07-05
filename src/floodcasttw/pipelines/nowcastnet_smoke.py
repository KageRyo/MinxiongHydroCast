"""Run NowcastNet adapter checks without committing external assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from floodcasttw.models.assets import write_manifest
from floodcasttw.models.nowcastnet_adapter import NowcastNetAdapter, NowcastNetConfig

PIPELINE_NAME = "nowcastnet_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check NowcastNet adapter prerequisites.")
    parser.add_argument("--code-dir", type=Path, default=Path("data/external/nowcastnet/code"))
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--radar-dataset", type=Path, default=None)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--input-length", type=int, default=9)
    parser.add_argument("--total-length", type=int, default=29)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--output", type=Path, default=Path("data/processed/nowcastnet_smoke.json"))
    parser.add_argument("--manifest-output", type=Path, default=None)
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    adapter = NowcastNetAdapter(
        NowcastNetConfig(
            code_dir=args.code_dir,
            checkpoint=args.checkpoint,
            radar_dataset=args.radar_dataset,
            device=args.device,
            input_length=args.input_length,
            total_length=args.total_length,
            image_height=args.height,
            image_width=args.width,
        )
    )
    result = {
        "healthcheck": adapter.healthcheck(),
        "smoke_test": adapter.smoke_test_with_persistence(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.manifest_output:
        write_manifest(adapter.asset_manifest(), args.manifest_output)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={
            "code_dir": str(args.code_dir),
            "checkpoint": str(args.checkpoint) if args.checkpoint else "",
            "radar_dataset": str(args.radar_dataset) if args.radar_dataset else "",
        },
        outputs={
            "smoke_result": str(args.output),
            "asset_manifest": str(args.manifest_output) if args.manifest_output else "",
        },
        metadata={
            "adapter_available": result["healthcheck"]["available"],
            "missing_assets": result["healthcheck"]["assets"]["missing_required"],
            "input_shape": result["smoke_test"]["input_shape"],
            "prediction_shape": result["smoke_test"]["prediction_shape"],
        },
    )
    record_run(
        summary_output=args.summary_output,
        log_output=args.log_output,
        summary=summary,
    )
    print(f"[OK] Wrote NowcastNet smoke result to {args.output}")


if __name__ == "__main__":
    main()
