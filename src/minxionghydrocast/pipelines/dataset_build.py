"""Build a checksummed, event-split CWA radar research dataset outside Git."""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion.cwa_event_collector import (
    build_event_plan,
    download_event_frames,
    load_event_collection,
    load_history_index,
    write_event_collection,
    write_event_plan,
)
from minxionghydrocast.ingestion.cwa_history import (
    CwaHistoryRequest,
    fetch_history_index,
    write_history_index,
)
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    atomic_write_schema,
    require_external_research_root,
    sha256_file,
)
from minxionghydrocast.models.dataset_schemas import (
    REQUIRED_SPLITS,
    ArtifactRecord,
    DatasetCatalog,
    DatasetVerificationReport,
    EventCatalogEntry,
    EventModelComparison,
    PersistenceMetrics,
    RadarDatasetEvent,
    RadarDatasetManifest,
    WeightedTinyUnetAssessment,
)
from minxionghydrocast.pipelines.radar_tensor_conversion import (
    convert_source,
    load_tensor_archive,
    write_tensor_archive,
)
from minxionghydrocast.pipelines.tensor_baseline_evaluation import (
    evaluate_persistence_tensor_archive,
    write_evaluation_result as write_persistence_evaluation_result,
)
from minxionghydrocast.pipelines.torch_baseline_evaluation import (
    evaluate_torch_baseline_comparison,
    write_evaluation_result as write_torch_evaluation_result,
)
from minxionghydrocast.pipelines.torch_baseline_training import (
    TorchTrainingConfig,
    train_tiny_unet_archive,
)

PIPELINE_NAME = "dataset_build"
TAIPEI_TZ = ZoneInfo("Asia/Taipei")
LOGGER = logging.getLogger(__name__)


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_dataset_manifest(path: Path) -> RadarDatasetManifest:
    return RadarDatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))


def catalog_artifacts(catalog: DatasetCatalog) -> list[ArtifactRecord]:
    artifacts = [catalog.manifest, catalog.history_index, *catalog.combined_archives.values()]
    for event in catalog.events:
        artifacts.extend(event.artifacts)
    if catalog.weighted_tiny_unet is not None:
        artifacts.extend(
            [
                catalog.weighted_tiny_unet.checkpoint,
                catalog.weighted_tiny_unet.training_result,
            ]
        )
        artifacts.extend(
            comparison.artifact for comparison in catalog.weighted_tiny_unet.comparisons
        )
    return artifacts


def resolve_catalog_artifact_path(
    *,
    artifact: ArtifactRecord,
    layout: ResearchLayout,
    repository_root: Path,
) -> Path:
    candidate = Path(artifact.path)
    if artifact.kind == "tracked_dataset_manifest":
        return candidate if candidate.is_absolute() else repository_root / candidate
    if candidate.is_absolute():
        raise ValueError(f"research artifact path must be relative: {artifact.path}")
    resolved = (layout.root / candidate).resolve()
    try:
        resolved.relative_to(layout.root)
    except ValueError as exc:
        raise ValueError(f"research artifact escapes root: {artifact.path}") from exc
    return resolved


def verify_dataset_catalog(
    *,
    catalog_path: Path,
    repository_root: Path,
) -> tuple[DatasetVerificationReport, Path]:
    catalog = DatasetCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    layout = ResearchLayout(Path(catalog.research_root))
    require_external_research_root(layout, repository_root=repository_root)
    mismatches = []
    total_bytes = 0
    artifacts = catalog_artifacts(catalog)
    seen_paths: set[Path] = set()
    for artifact in artifacts:
        try:
            path = resolve_catalog_artifact_path(
                artifact=artifact,
                layout=layout,
                repository_root=repository_root,
            ).resolve()
        except ValueError as exc:
            mismatches.append(str(exc))
            continue
        if path in seen_paths:
            mismatches.append(f"duplicate artifact path: {artifact.path}")
            continue
        seen_paths.add(path)
        if not path.is_file():
            mismatches.append(f"missing artifact: {artifact.path}")
            continue
        actual_bytes = path.stat().st_size
        total_bytes += actual_bytes
        if actual_bytes != artifact.bytes:
            mismatches.append(
                f"size mismatch: {artifact.path} expected={artifact.bytes} actual={actual_bytes}"
            )
        actual_sha256 = sha256_file(path)
        if actual_sha256 != artifact.sha256:
            mismatches.append(f"sha256 mismatch: {artifact.path}")
    catalog_artifact = artifact_record(layout, catalog_path, kind="dataset_catalog")
    report = DatasetVerificationReport(
        verified_at=datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        status="error" if mismatches else "ok",
        catalog=catalog_artifact,
        artifact_count=len(artifacts),
        total_bytes=total_bytes,
        mismatches=mismatches,
    )
    report_path = layout.catalog / "dataset_verification.json"
    atomic_write_schema(report_path, report)
    return report, report_path


def expected_frame_count(event: RadarDatasetEvent, *, cadence_minutes: int) -> int:
    duration = parse_iso_datetime(event.end_time) - parse_iso_datetime(event.start_time)
    interval_seconds = cadence_minutes * 60
    quotient, remainder = divmod(int(duration.total_seconds()), interval_seconds)
    if remainder:
        raise ValueError(f"{event.event_id}: event window is not cadence-aligned")
    return quotient + 1


def persistence_metrics(result: dict[str, Any]) -> PersistenceMetrics:
    event_metrics = result["event_metrics"]
    return PersistenceMetrics(
        rmse=float(result["rmse"]),
        csi=float(event_metrics["csi"]),
        pod=float(event_metrics["pod"]),
        far=float(event_metrics["far"]),
        lead_time_metrics=result["lead_time_metrics"],
    )


def build_event(
    *,
    event: RadarDatasetEvent,
    split: str,
    manifest: RadarDatasetManifest,
    history_index: dict[str, Any],
    layout: ResearchLayout,
    authorization: str,
    skip_download: bool,
    verify_tls: bool,
    timeout: int,
    max_workers: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
) -> EventCatalogEntry:
    dataset = manifest.dataset
    LOGGER.info("event_build_started event_id=%s split=%s", event.event_id, split)
    plan_path = layout.events / f"{event.event_id}_plan.json"
    collection_path = layout.events / f"{event.event_id}_collection.json"
    raw_root = layout.raw / "radar"
    tensor_path = layout.tensors / f"{event.event_id}.npz"
    persistence_path = layout.reports / f"{event.event_id}_persistence.json"

    plan = build_event_plan(
        history_index,
        event_id=event.event_id,
        start_time=event.start_time,
        end_time=event.end_time,
    )
    required_frames = expected_frame_count(event, cadence_minutes=dataset.cadence_minutes)
    if plan.frame_count != required_frames:
        raise ValueError(
            f"{event.event_id}: history contains {plan.frame_count}/{required_frames} frames"
        )
    write_event_plan(plan_path, plan)
    LOGGER.info(
        "event_plan_ready event_id=%s frame_count=%d",
        event.event_id,
        plan.frame_count,
    )

    if skip_download:
        if not collection_path.is_file():
            raise FileNotFoundError(f"missing existing collection: {collection_path}")
        collection = load_event_collection(collection_path)
        if collection.event_id != event.event_id or collection.data_id != dataset.data_id:
            raise ValueError(f"{event.event_id}: existing collection identity does not match")
        frame_paths = [Path(frame.output_path) for frame in collection.frames]
    else:
        LOGGER.info("event_download_started event_id=%s", event.event_id)
        collection = download_event_frames(
            plan,
            output_dir=raw_root,
            authorization=authorization,
            timeout=timeout,
            skip_existing=True,
            verify_tls=verify_tls,
            max_workers=max_workers,
            retry_attempts=retry_attempts,
            retry_backoff_seconds=retry_backoff_seconds,
        )
        write_event_collection(collection_path, collection)
        frame_paths = [Path(frame.output_path) for frame in collection.frames]
    if len(frame_paths) != required_frames or not all(path.is_file() for path in frame_paths):
        raise ValueError(f"{event.event_id}: collection is incomplete")

    LOGGER.info("event_tensor_conversion_started event_id=%s", event.event_id)
    input_tensor, target_tensor, spec, metadata, _record_count = convert_source(
        input_path=collection_path,
        source_format=dataset.source_format,
        event_id=event.event_id,
        input_length=dataset.input_length,
        prediction_length=dataset.prediction_length,
        cadence_minutes=dataset.cadence_minutes,
        units=dataset.units,
        crs=dataset.crs,
        window_stride_frames=dataset.window_stride_frames,
    )
    write_tensor_archive(
        output_path=tensor_path,
        input_tensor=input_tensor,
        target_tensor=target_tensor,
        spec=spec,
        metadata={**metadata, "model_split": split},
    )
    persistence = evaluate_persistence_tensor_archive(
        archive_path=tensor_path,
        event_threshold_mm=dataset.event_threshold,
    )
    write_persistence_evaluation_result(persistence, persistence_path)
    LOGGER.info(
        "event_build_completed event_id=%s windows=%s persistence_csi=%s",
        event.event_id,
        metadata.get("window_count", 1),
        persistence["event_metrics"]["csi"],
    )

    artifacts = [
        artifact_record(layout, plan_path, kind="event_plan"),
        artifact_record(layout, collection_path, kind="event_collection"),
        artifact_record(layout, tensor_path, kind="tensor_archive"),
        artifact_record(layout, persistence_path, kind="persistence_evaluation"),
    ]
    artifacts.extend(
        artifact_record(layout, path, kind="raw_radar_frame") for path in frame_paths
    )
    return EventCatalogEntry(
        event_id=event.event_id,
        split=split,
        region=event.region,
        source_data_id=dataset.data_id,
        start_time=event.start_time,
        end_time=event.end_time,
        frame_count=len(frame_paths),
        window_count=int(metadata.get("window_count", 1)),
        artifacts=artifacts,
        persistence=persistence_metrics(persistence),
    )


def combine_split_archives(
    *,
    manifest: RadarDatasetManifest,
    layout: ResearchLayout,
    split: str,
) -> Path:
    event_ids = manifest.splits[split]
    archives = [load_tensor_archive(layout.tensors / f"{event_id}.npz") for event_id in event_ids]
    specs = [archive["spec"] for archive in archives]
    if any(spec != specs[0] for spec in specs[1:]):
        raise ValueError(f"{split} tensor specs are not identical")
    inputs = [np.asarray(archive["input"], dtype=np.float32) for archive in archives]
    targets = [np.asarray(archive["target"], dtype=np.float32) for archive in archives]
    if any(array.ndim != 5 for array in inputs + targets):
        raise ValueError(f"{split} archives must use sliding-window layout")
    sample_counts = [int(array.shape[0]) for array in inputs]
    metadata = {
        "archive_layout": "multi_event_sliding_window",
        "model_split": split,
        "event_ids": event_ids,
        "event_sample_counts": dict(zip(event_ids, sample_counts, strict=True)),
        "window_count": sum(sample_counts),
        "nodata_values": archives[0]["metadata"].get("nodata_values", []),
        "source_archives": [f"tensors/{event_id}.npz" for event_id in event_ids],
    }
    output = layout.tensors / f"{split}_events.npz"
    spec_payload = json.dumps(specs[0], ensure_ascii=False)
    np.savez_compressed(
        output,
        input=np.concatenate(inputs, axis=0),
        target=np.concatenate(targets, axis=0),
        spec=spec_payload,
        metadata=json.dumps(metadata, ensure_ascii=False),
    )
    return output


def comparison_metrics(
    *,
    result: dict[str, Any],
    split: str,
    artifact: ArtifactRecord,
) -> EventModelComparison:
    persistence = result["models"]["PersistenceNowcaster"]
    tiny_unet = result["models"]["TinyUNetNowcaster"]
    return EventModelComparison(
        event_id=str(result["event_id"]),
        split=split,
        persistence_rmse=float(persistence["rmse"]),
        persistence_csi=float(persistence["event_metrics"]["csi"]),
        tiny_unet_rmse=float(tiny_unet["rmse"]),
        tiny_unet_csi=float(tiny_unet["event_metrics"]["csi"]),
        rmse_delta_tiny_unet_minus_persistence=float(
            result["comparison"]["rmse_delta_tiny_unet_minus_persistence"]
        ),
        csi_delta_tiny_unet_minus_persistence=float(
            result["comparison"]["csi_delta_tiny_unet_minus_persistence"]
        ),
        persistence_lead_time_metrics=persistence["lead_time_metrics"],
        tiny_unet_lead_time_metrics=tiny_unet["lead_time_metrics"],
        artifact=artifact,
    )


def promotion_gate_failures(comparisons: list[EventModelComparison]) -> list[str]:
    failures = []
    validation_comparisons = [
        comparison for comparison in comparisons if comparison.split == "validation"
    ]
    test_comparisons = [comparison for comparison in comparisons if comparison.split == "test"]
    if not validation_comparisons:
        failures.append("no independent validation comparison was produced")
    if not test_comparisons:
        failures.append("no independent test comparisons were produced")
    for comparison in comparisons:
        if comparison.tiny_unet_rmse >= comparison.persistence_rmse:
            failures.append(f"{comparison.event_id}: aggregate RMSE did not beat persistence")
        if comparison.tiny_unet_csi <= comparison.persistence_csi:
            failures.append(f"{comparison.event_id}: aggregate CSI did not beat persistence")
        for persistence_lead, tiny_lead in zip(
            comparison.persistence_lead_time_metrics,
            comparison.tiny_unet_lead_time_metrics,
            strict=True,
        ):
            lead_time = persistence_lead.lead_time_minutes
            if tiny_lead.rmse >= persistence_lead.rmse:
                failures.append(
                    f"{comparison.event_id}: {lead_time}-minute RMSE did not beat persistence"
                )
            if tiny_lead.event_metrics.csi <= persistence_lead.event_metrics.csi:
                failures.append(
                    f"{comparison.event_id}: {lead_time}-minute CSI did not beat persistence"
                )
    return failures


def train_and_evaluate_weighted_tiny_unet(
    *,
    manifest: RadarDatasetManifest,
    layout: ResearchLayout,
    epochs: int,
    learning_rate: float,
    hidden_channels: int,
    batch_size: int,
    event_weight: float,
    early_stopping_patience: int,
    device: str,
    multi_gpu: bool,
) -> WeightedTinyUnetAssessment:
    output_dir = layout.models / "weighted_tiny_unet"
    LOGGER.info(
        "weighted_tiny_unet_training_started train_events=%s validation_events=%s",
        manifest.splits["train"],
        manifest.splits["validation"],
    )
    result = train_tiny_unet_archive(
        TorchTrainingConfig(
            archive_path=layout.tensors / "train_events.npz",
            validation_archive_path=layout.tensors / "validation_events.npz",
            output_dir=output_dir,
            epochs=epochs,
            learning_rate=learning_rate,
            hidden_channels=hidden_channels,
            device=device,
            multi_gpu=multi_gpu,
            batch_size=batch_size,
            loss_function="weighted_mse",
            event_threshold=manifest.dataset.event_threshold,
            event_weight=event_weight,
            validation_fraction=0.0,
            early_stopping_patience=early_stopping_patience,
        )
    )
    checkpoint_path = Path(result.checkpoint)
    training_result_path = output_dir / "tiny_unet_training_result.json"
    comparisons = []
    for split in ("validation", "test"):
        for event_id in manifest.splits[split]:
            LOGGER.info(
                "weighted_tiny_unet_evaluation_started event_id=%s split=%s",
                event_id,
                split,
            )
            comparison_path = layout.reports / f"{event_id}_weighted_tiny_unet.json"
            comparison = evaluate_torch_baseline_comparison(
                archive_path=layout.tensors / f"{event_id}.npz",
                checkpoint_path=checkpoint_path,
                event_threshold=manifest.dataset.event_threshold,
                device=device,
                batch_size=batch_size,
            )
            write_torch_evaluation_result(comparison, comparison_path)
            comparisons.append(
                comparison_metrics(
                    result=comparison,
                    split=split,
                    artifact=artifact_record(
                        layout,
                        comparison_path,
                        kind="weighted_tiny_unet_evaluation",
                    ),
                )
            )
    failures = promotion_gate_failures(comparisons)
    LOGGER.info("weighted_tiny_unet_evaluation_completed gate_failures=%d", len(failures))
    return WeightedTinyUnetAssessment(
        checkpoint=artifact_record(layout, checkpoint_path, kind="model_checkpoint"),
        training_result=artifact_record(
            layout,
            training_result_path,
            kind="model_training_result",
        ),
        training_event_ids=manifest.splits["train"],
        validation_event_ids=manifest.splits["validation"],
        comparisons=comparisons,
        promotion_gate_passed=not failures,
        promotion_gate_failures=failures,
    )


def build_dataset(
    *,
    manifest_path: Path,
    research_root: Path,
    history_index_path: Path | None,
    authorization: str,
    skip_download: bool = False,
    verify_tls: bool = True,
    timeout: int = 60,
    max_workers: int = 4,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 1.0,
) -> tuple[DatasetCatalog, Path]:
    manifest = load_dataset_manifest(manifest_path)
    layout = ResearchLayout(research_root)
    require_external_research_root(layout, repository_root=Path.cwd())
    layout.ensure()
    LOGGER.info(
        "dataset_build_started root=%s events=%d",
        layout.root,
        len(manifest.events),
    )
    if history_index_path is None:
        history_index_path = layout.raw / f"{manifest.dataset.data_id}_history_latest.json"
        history = fetch_history_index(
            CwaHistoryRequest(data_id=manifest.dataset.data_id),
            authorization=authorization,
            timeout=timeout,
            verify_tls=verify_tls,
        )
        write_history_index(history_index_path, history)
        history_index = history.model_dump(mode="json")
    else:
        history_index = load_history_index(history_index_path)
    if history_index.get("data_id") != manifest.dataset.data_id:
        raise ValueError("history index data_id does not match dataset manifest")

    entries = []
    for event in manifest.events:
        entries.append(
            build_event(
                event=event,
                split=manifest.split_for(event.event_id),
                manifest=manifest,
                history_index=history_index,
                layout=layout,
                authorization=authorization,
                skip_download=skip_download,
                verify_tls=verify_tls,
                timeout=timeout,
                max_workers=max_workers,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
            )
        )

    combined_archives = {}
    for split in REQUIRED_SPLITS:
        LOGGER.info("split_archive_started split=%s", split)
        archive = combine_split_archives(manifest=manifest, layout=layout, split=split)
        combined_archives[split] = artifact_record(
            layout,
            archive,
            kind=f"{split}_combined_tensor_archive",
        )
    dataset_id = f"{manifest.dataset.data_id.lower().replace('-', '_')}_event_dataset"
    blockers = [
        "weighted Tiny U-Net has not passed independent-event promotion gates",
        "forecast publication remains disabled",
    ]
    catalog = DatasetCatalog(
        generated_at=datetime.now(TAIPEI_TZ).isoformat(timespec="seconds"),
        dataset_id=dataset_id,
        research_root=str(layout.root),
        source_data_id=manifest.dataset.data_id,
        manifest=ArtifactRecord(
            kind="tracked_dataset_manifest",
            path=str(manifest_path),
            sha256=sha256_file(manifest_path),
            bytes=manifest_path.stat().st_size,
        ),
        history_index=artifact_record(layout, history_index_path, kind="history_index"),
        split_counts={split: len(manifest.splits[split]) for split in REQUIRED_SPLITS},
        events=entries,
        combined_archives=combined_archives,
        forecast_publication_ready=False,
        forecast_publication_blockers=blockers,
    )
    catalog_path = layout.catalog / "dataset_catalog.json"
    atomic_write_schema(catalog_path, catalog)
    LOGGER.info("dataset_build_completed catalog=%s", catalog_path)
    return catalog, catalog_path


def attach_weighted_model_assessment(
    *,
    catalog: DatasetCatalog,
    manifest_path: Path,
    research_root: Path,
    epochs: int,
    learning_rate: float,
    hidden_channels: int,
    batch_size: int,
    event_weight: float,
    early_stopping_patience: int,
    device: str,
    multi_gpu: bool,
) -> tuple[DatasetCatalog, Path]:
    manifest = load_dataset_manifest(manifest_path)
    layout = ResearchLayout(research_root)
    assessment = train_and_evaluate_weighted_tiny_unet(
        manifest=manifest,
        layout=layout,
        epochs=epochs,
        learning_rate=learning_rate,
        hidden_channels=hidden_channels,
        batch_size=batch_size,
        event_weight=event_weight,
        early_stopping_patience=early_stopping_patience,
        device=device,
        multi_gpu=multi_gpu,
    )
    blockers = [] if assessment.promotion_gate_passed else [
        "weighted Tiny U-Net did not pass independent-event promotion gates",
        *assessment.promotion_gate_failures,
    ]
    updated = DatasetCatalog.model_validate(
        {
            **catalog.model_dump(),
            "weighted_tiny_unet": assessment,
            "forecast_publication_ready": assessment.promotion_gate_passed,
            "forecast_publication_blockers": blockers,
        }
    )
    catalog_path = layout.catalog / "dataset_catalog.json"
    atomic_write_schema(catalog_path, updated)
    return updated, catalog_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a checksummed event-split CWA radar dataset outside Git."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/samples/event_split_manifest.json"),
    )
    parser.add_argument("--root", type=Path, default=get_settings().research_root)
    parser.add_argument("--history-index", type=Path, default=None)
    parser.add_argument("--api-key-env", default="CWA_API_KEY")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--insecure-tls", action="store_true")
    parser.add_argument("--train-weighted-unet", action="store_true")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--hidden-channels", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--event-weight", type=float, default=4.0)
    parser.add_argument("--early-stopping-patience", type=int, default=5)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--multi-gpu", action="store_true")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    started_at, start_timer = start_run()
    try:
        catalog, catalog_path = build_dataset(
            manifest_path=args.manifest,
            research_root=args.root,
            history_index_path=args.history_index,
            authorization=os.getenv(args.api_key_env, ""),
            skip_download=args.skip_download,
            verify_tls=not args.insecure_tls,
            timeout=args.timeout,
            max_workers=args.max_workers,
            retry_attempts=args.retry_attempts,
            retry_backoff_seconds=args.retry_backoff_seconds,
        )
        if args.train_weighted_unet:
            catalog, catalog_path = attach_weighted_model_assessment(
                catalog=catalog,
                manifest_path=args.manifest,
                research_root=args.root,
                epochs=args.epochs,
                learning_rate=args.learning_rate,
                hidden_channels=args.hidden_channels,
                batch_size=args.batch_size,
                event_weight=args.event_weight,
                early_stopping_patience=args.early_stopping_patience,
                device=args.device,
                multi_gpu=args.multi_gpu,
            )
        verification, verification_path = verify_dataset_catalog(
            catalog_path=catalog_path,
            repository_root=Path.cwd(),
        )
        if verification.status != "ok":
            raise RuntimeError(
                "dataset catalog verification failed: " + "; ".join(verification.mismatches)
            )
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="ok",
            started_at=started_at,
            start_timer=start_timer,
            inputs={"manifest": str(args.manifest)},
            outputs={
                "catalog": str(catalog_path),
                "verification": str(verification_path),
            },
            row_counts={
                "events": len(catalog.events),
                "train_events": catalog.split_counts["train"],
                "validation_events": catalog.split_counts["validation"],
                "test_events": catalog.split_counts["test"],
                "verified_artifacts": verification.artifact_count,
            },
            metadata={
                "research_root": str(args.root.expanduser()),
                "source_data_id": catalog.source_data_id,
                "api_key_env": args.api_key_env,
                "api_key_present": bool(os.getenv(args.api_key_env, "")),
                "verify_tls": not args.insecure_tls,
                "skip_download": args.skip_download,
                "train_weighted_unet": args.train_weighted_unet,
                "forecast_publication_ready": catalog.forecast_publication_ready,
                "verified_artifact_bytes": verification.total_bytes,
            },
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        LOGGER.info("dataset_catalog_written path=%s", catalog_path)
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=str(exc),
            started_at=started_at,
            start_timer=start_timer,
            inputs={"manifest": str(args.manifest)},
            outputs={"catalog": ""},
            metadata={
                "research_root": str(args.root.expanduser()),
                "api_key_env": args.api_key_env,
                "api_key_present": bool(os.getenv(args.api_key_env, "")),
                "verify_tls": not args.insecure_tls,
                "skip_download": args.skip_download,
            },
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        LOGGER.error("dataset_build_failed error=%s", exc)
        raise SystemExit(f"[ERROR] {exc}") from exc


if __name__ == "__main__":
    main()
