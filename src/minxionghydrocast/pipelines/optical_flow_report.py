"""Build a public-safe, event-split comparison report for three nowcasting models."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.dataset_schemas import RadarDatasetManifest
from minxionghydrocast.models.evaluation_schemas import (
    OpticalFlowAggregateReportSchema,
    OpticalFlowComparisonSchema,
    PublicEventReportSchema,
    TorchBaselineComparisonSchema,
)

PIPELINE_NAME = "optical_flow_report"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
MODEL_NAMES = ("PersistenceNowcaster", "OpticalFlowNowcaster", "TinyUNetNowcaster")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evaluation report must be a JSON object: {path}")
    return payload


def _round(value: float) -> float:
    return round(float(value), 6)


def _event_metrics_payload(metrics: Any) -> dict[str, float | int]:
    return metrics.model_dump(mode="json")


def _public_model_metrics(metrics: Any) -> dict[str, Any]:
    return {
        "rmse": _round(metrics.rmse),
        "mae": _round(metrics.mae) if hasattr(metrics, "mae") else None,
        "event_metrics": _event_metrics_payload(metrics.event_metrics),
        "valid_pixel_count": metrics.valid_pixel_count,
        "ignored_pixel_count": metrics.ignored_pixel_count,
        "lead_time_metrics": [
            {
                "lead_index": lead.lead_index,
                "lead_time_minutes": lead.lead_time_minutes,
                "rmse": _round(lead.rmse),
                "mae": _round(lead.mae) if hasattr(lead, "mae") else None,
                "event_metrics": _event_metrics_payload(lead.event_metrics),
                "valid_pixel_count": lead.valid_pixel_count,
                "ignored_pixel_count": lead.ignored_pixel_count,
            }
            for lead in metrics.lead_time_metrics
        ],
    }


def _assert_split_metadata(*, metadata: dict[str, Any], event_id: str, split: str) -> None:
    reported_split = metadata.get("model_split")
    if reported_split is not None and reported_split != split:
        raise ValueError(
            f"{event_id}: evaluation metadata split {reported_split!r} does not match {split!r}"
        )


def _assert_persistence_matches(
    *,
    event_id: str,
    optical: OpticalFlowComparisonSchema,
    tiny_unet: TorchBaselineComparisonSchema,
) -> None:
    optical_persistence = optical.models["PersistenceNowcaster"]
    tiny_persistence = tiny_unet.models["PersistenceNowcaster"]
    if abs(optical_persistence.rmse - tiny_persistence.rmse) > 1e-5:
        raise ValueError(f"{event_id}: persistence RMSE differs between comparison reports")
    if abs(
        optical_persistence.event_metrics.csi - tiny_persistence.event_metrics.csi
    ) > 1e-5:
        raise ValueError(f"{event_id}: persistence CSI differs between comparison reports")
    optical_leads = optical_persistence.lead_time_metrics
    tiny_leads = tiny_persistence.lead_time_metrics
    if [lead.lead_time_minutes for lead in optical_leads] != [
        lead.lead_time_minutes for lead in tiny_leads
    ]:
        raise ValueError(f"{event_id}: persistence lead-time grids differ between reports")


def _event_report(
    *,
    event: Any,
    split: str,
    optical: OpticalFlowComparisonSchema,
    tiny_unet: TorchBaselineComparisonSchema | None,
) -> PublicEventReportSchema:
    if optical.event_id != event.event_id:
        raise ValueError(
            f"optical-flow report event mismatch: {optical.event_id!r} != {event.event_id!r}"
        )
    if tiny_unet is not None and tiny_unet.event_id != event.event_id:
        raise ValueError(
            f"Tiny U-Net report event mismatch: {tiny_unet.event_id!r} != {event.event_id!r}"
        )
    models = {
        name: _public_model_metrics(optical.models[name])
        for name in ("PersistenceNowcaster", "OpticalFlowNowcaster")
    }
    if tiny_unet is not None:
        _assert_persistence_matches(event_id=event.event_id, optical=optical, tiny_unet=tiny_unet)
        models["TinyUNetNowcaster"] = _public_model_metrics(
            tiny_unet.models["TinyUNetNowcaster"]
        )
    return PublicEventReportSchema.model_validate(
        {
            "event_id": event.event_id,
            "split": split,
            "region": event.region,
            "event_type": event.event_type,
            "models": models,
        }
    )


def _event_metric_totals(metrics: list[dict[str, Any]]) -> dict[str, int]:
    fields = ("hits", "misses", "false_alarms", "correct_negatives")
    return {field: sum(int(item["event_metrics"][field]) for item in metrics) for field in fields}


def _derived_event_metrics(totals: dict[str, int]) -> dict[str, float | int]:
    hits = totals["hits"]
    misses = totals["misses"]
    false_alarms = totals["false_alarms"]
    denominator = hits + misses + false_alarms
    pod_denominator = hits + misses
    far_denominator = hits + false_alarms
    return {
        **totals,
        "csi": _round(hits / denominator if denominator else 0.0),
        "pod": _round(hits / pod_denominator if pod_denominator else 0.0),
        "far": _round(false_alarms / far_denominator if far_denominator else 0.0),
    }


def _aggregate_model_metrics(metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not metrics:
        raise ValueError("cannot aggregate an empty model result set")
    valid_pixel_count = sum(int(item["valid_pixel_count"]) for item in metrics)
    ignored_pixel_count = sum(int(item["ignored_pixel_count"]) for item in metrics)
    squared_error = sum(
        float(item["rmse"]) ** 2 * int(item["valid_pixel_count"]) for item in metrics
    )
    mae_values = [item["mae"] for item in metrics]
    mae_value = None
    if all(value is not None for value in mae_values):
        absolute_error = sum(
            float(item["mae"]) * int(item["valid_pixel_count"]) for item in metrics
        )
        mae_value = _round(absolute_error / valid_pixel_count)

    lead_times = [
        lead["lead_time_minutes"]
        for lead in metrics[0]["lead_time_metrics"]
    ]
    if any(
        [lead["lead_time_minutes"] for lead in item["lead_time_metrics"]] != lead_times
        for item in metrics[1:]
    ):
        raise ValueError("model results use different lead-time grids")
    lead_time_metrics = []
    for lead_index, lead_time in enumerate(lead_times):
        lead_results = [item["lead_time_metrics"][lead_index] for item in metrics]
        lead_valid = sum(int(item["valid_pixel_count"]) for item in lead_results)
        lead_ignored = sum(int(item["ignored_pixel_count"]) for item in lead_results)
        lead_squared_error = sum(
            float(item["rmse"]) ** 2 * int(item["valid_pixel_count"])
            for item in lead_results
        )
        lead_mae_values = [item["mae"] for item in lead_results]
        lead_mae = None
        if all(value is not None for value in lead_mae_values):
            lead_absolute_error = sum(
                float(item["mae"]) * int(item["valid_pixel_count"])
                for item in lead_results
            )
            lead_mae = _round(lead_absolute_error / lead_valid)
        lead_time_metrics.append(
            {
                "lead_index": lead_index,
                "lead_time_minutes": lead_time,
                "rmse": _round(math.sqrt(lead_squared_error / lead_valid)),
                "mae": lead_mae,
                "event_metrics": _derived_event_metrics(_event_metric_totals(lead_results)),
                "valid_pixel_count": lead_valid,
                "ignored_pixel_count": lead_ignored,
            }
        )
    return {
        "rmse": _round(math.sqrt(squared_error / valid_pixel_count)),
        "mae": mae_value,
        "event_metrics": _derived_event_metrics(_event_metric_totals(metrics)),
        "valid_pixel_count": valid_pixel_count,
        "ignored_pixel_count": ignored_pixel_count,
        "lead_time_metrics": lead_time_metrics,
    }


def build_public_optical_flow_report(
    *,
    manifest_path: Path,
    optical_flow_dir: Path,
    tiny_unet_dir: Path,
    require_tiny_unet: bool = True,
) -> dict[str, Any]:
    """Build a report without copying private paths, artifacts, or raw evidence."""

    manifest = RadarDatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    split_by_id = {
        event_id: split
        for split, event_ids in manifest.splits.items()
        for event_id in event_ids
    }
    event_reports = []
    for event in manifest.events:
        split = split_by_id[event.event_id]
        optical_path = optical_flow_dir / f"{event.event_id}_optical_flow.json"
        if not optical_path.is_file():
            raise FileNotFoundError(f"missing optical-flow evaluation: {optical_path}")
        optical = OpticalFlowComparisonSchema.model_validate_json(
            optical_path.read_text(encoding="utf-8")
        )
        _assert_split_metadata(metadata=optical.metadata, event_id=event.event_id, split=split)

        tiny_unet = None
        if split in {"validation", "test"}:
            tiny_path = tiny_unet_dir / f"{event.event_id}_weighted_tiny_unet.json"
            if not tiny_path.is_file():
                if require_tiny_unet:
                    raise FileNotFoundError(f"missing Tiny U-Net evaluation: {tiny_path}")
            else:
                tiny_unet = TorchBaselineComparisonSchema.model_validate_json(
                    tiny_path.read_text(encoding="utf-8")
                )
                _assert_split_metadata(
                    metadata=tiny_unet.metadata,
                    event_id=event.event_id,
                    split=split,
                )
        event_reports.append(
            _event_report(
                event=event,
                split=split,
                optical=optical,
                tiny_unet=tiny_unet,
            ).model_dump(
                mode="json"
            )
        )

    grouped: dict[str, list[dict[str, Any]]] = {"train": [], "validation": [], "test": []}
    for event_report in event_reports:
        grouped[event_report["split"]].append(event_report)
    grouped["independent"] = grouped["validation"] + grouped["test"]
    aggregate_by_split: dict[str, dict[str, Any]] = {}
    for split, reports in grouped.items():
        if not reports:
            continue
        model_names = set(reports[0]["models"])
        if any(set(report["models"]) != model_names for report in reports):
            raise ValueError(f"{split}: model coverage differs between event reports")
        aggregate_by_split[split] = {
            name: {
                **_aggregate_model_metrics([report["models"][name] for report in reports]),
                "event_count": len(reports),
            }
            for name in sorted(model_names)
        }

    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        "dataset_id": f"{manifest.dataset.data_id.lower().replace('-', '_')}_event_dataset",
        "source_data_id": manifest.dataset.data_id,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "split_strategy": manifest.split_strategy,
        "events": event_reports,
        "aggregate_by_split": aggregate_by_split,
    }
    return OpticalFlowAggregateReportSchema.model_validate(payload).model_dump(mode="json")


def write_public_report(report: dict[str, Any], output_path: Path) -> None:
    validated = OpticalFlowAggregateReportSchema.model_validate(report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(validated.model_dump_json(indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a public-safe Persistence/optical-flow/Tiny U-Net report."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/samples/event_split_manifest.json"),
    )
    parser.add_argument("--optical-flow-dir", type=Path, required=True)
    parser.add_argument("--tiny-unet-dir", type=Path, required=True)
    parser.add_argument("--allow-missing-tiny-unet", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/optical_flow_public_report.json"),
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    report = build_public_optical_flow_report(
        manifest_path=args.manifest,
        optical_flow_dir=args.optical_flow_dir,
        tiny_unet_dir=args.tiny_unet_dir,
        require_tiny_unet=not args.allow_missing_tiny_unet,
    )
    write_public_report(report, args.output)
    independent = report["aggregate_by_split"]["independent"]
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok",
        started_at=started_at,
        start_timer=start_timer,
        inputs={
            "manifest": str(args.manifest),
            "optical_flow_dir": str(args.optical_flow_dir),
            "tiny_unet_dir": str(args.tiny_unet_dir),
        },
        outputs={"report": str(args.output)},
        row_counts={"events": len(report["events"])},
        metrics={
            "independent_persistence_rmse": independent["PersistenceNowcaster"]["rmse"],
            "independent_optical_flow_rmse": independent["OpticalFlowNowcaster"]["rmse"],
            "independent_optical_flow_csi": independent["OpticalFlowNowcaster"][
                "event_metrics"
            ]["csi"],
        },
        metadata={
            "dataset_id": report["dataset_id"],
            "source_data_id": report["source_data_id"],
            "manifest_sha256": report["manifest_sha256"],
            "require_tiny_unet": not args.allow_missing_tiny_unet,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote public optical-flow report to {args.output}")


if __name__ == "__main__":
    main()
