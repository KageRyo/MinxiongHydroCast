"""Run NowcastNet adapter checks without committing external assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from floodcasttw.models.assets import write_manifest
from floodcasttw.models.nowcastnet_adapter import NowcastNetAdapter, NowcastNetConfig


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
    args = parser.parse_args()

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
    print(f"[OK] Wrote NowcastNet smoke result to {args.output}")


if __name__ == "__main__":
    main()
