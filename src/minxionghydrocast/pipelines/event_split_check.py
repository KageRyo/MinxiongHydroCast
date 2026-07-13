"""Validate the formal event split and discovered-candidate promotion gate."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.dataset_schemas import RadarDatasetManifest
from minxionghydrocast.models.event_splits import (
    DEFAULT_MANIFEST,
    EventSplitManifest,
    write_check_result,
)
from minxionghydrocast.pipelines.event_promotion import (
    validate_candidate_promotion_gate,
)

PIPELINE_NAME = "event_split_check"
LOGGER = logging.getLogger(__name__)


def check_event_split_manifest(
    *,
    manifest_path: Path,
    event_evidence_catalog_path: Path | None,
    repository_root: Path,
) -> dict[str, Any]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    result = EventSplitManifest.from_dict(payload).check()
    errors = result["errors"]
    if not isinstance(errors, list):
        raise TypeError("event split checker returned an invalid errors field")

    promotion_status = "not_run"
    try:
        manifest = RadarDatasetManifest.model_validate(payload)
    except ValidationError as exc:
        errors.append(f"dataset manifest schema validation failed: {exc}")
    else:
        try:
            validate_candidate_promotion_gate(
                manifest=manifest,
                event_evidence_catalog_path=event_evidence_catalog_path,
                repository_root=repository_root,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            promotion_status = "error"
            errors.append(str(exc))
        else:
            promotion_status = "ok"

    result["status"] = "error" if errors else "ok"
    result["candidate_promotion_gate"] = promotion_status
    result["event_evidence_catalog"] = (
        str(event_evidence_catalog_path) if event_evidence_catalog_path else None
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check event splits and reviewed-candidate promotion readiness."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--event-evidence-catalog", type=Path, default=None)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/event_split_check.json"),
    )
    parser.add_argument("--require-ok", action="store_true")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    started_at, start_timer = start_run()
    try:
        result = check_event_split_manifest(
            manifest_path=args.manifest,
            event_evidence_catalog_path=args.event_evidence_catalog,
            repository_root=args.repository_root,
        )
        write_check_result(result, args.output)
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=str(exc),
            started_at=started_at,
            start_timer=start_timer,
            inputs={
                "manifest": str(args.manifest),
                "event_evidence_catalog": (
                    str(args.event_evidence_catalog) if args.event_evidence_catalog else ""
                ),
            },
            outputs={"check_result": ""},
        )
        record_run(
            summary_output=args.summary_output,
            log_output=args.log_output,
            summary=summary,
        )
        LOGGER.error("event split check failed: %s", exc)
        raise SystemExit(1) from exc

    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status=str(result["status"]),
        failure_reason="; ".join(result["errors"]),
        started_at=started_at,
        start_timer=start_timer,
        inputs={
            "manifest": str(args.manifest),
            "event_evidence_catalog": (
                str(args.event_evidence_catalog) if args.event_evidence_catalog else ""
            ),
        },
        outputs={"check_result": str(args.output)},
        row_counts={
            "events": result["event_count"],
            "train": result["split_counts"]["train"],
            "validation": result["split_counts"]["validation"],
            "test": result["split_counts"]["test"],
        },
        metadata={
            "target": result["target"],
            "require_ok": args.require_ok,
            "candidate_promotion_gate": result["candidate_promotion_gate"],
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    LOGGER.info("event split check written: path=%s status=%s", args.output, result["status"])
    if args.require_ok and result["status"] != "ok":
        raise SystemExit("event split manifest failed validation")


if __name__ == "__main__":
    main()
