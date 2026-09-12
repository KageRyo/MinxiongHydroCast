"""Orchestrate incremental radar-event discovery and evidence preservation."""

from __future__ import annotations

import argparse
import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from minxionghydrocast.config import get_settings
from minxionghydrocast.ingestion.cwa_event_collector import (
    HttpResponse as FrameHttpResponse,
    build_event_plan,
    download_event_frames,
)
from minxionghydrocast.ingestion.cwa_file_api import HttpResponse as FileHttpResponse
from minxionghydrocast.ingestion.cwa_history import (
    CwaHistoryIndex,
    CwaHistoryRequest,
    HttpResponse as HistoryHttpResponse,
    fetch_history_index,
)
from minxionghydrocast.ingestion.cwa_rainfall_api import CwaRainGaugeAdapter
from minxionghydrocast.ingestion.http_client import verified_get
from minxionghydrocast.ingestion.source_adapter import SourceResult
from minxionghydrocast.ingestion.wra_rainfall_alert_api import WraRainfallAlertAdapter
from minxionghydrocast.io.research_store import (
    ResearchLayout,
    artifact_record,
    prune_cache,
    require_external_research_root,
    write_schema_if_changed,
)
from minxionghydrocast.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)
from minxionghydrocast.models.event_evidence_schemas import (
    DiscoveryConfig,
    DiscoveryCursor,
    EventEvidenceCatalog,
    RadarFrameMetric,
    aware_datetime,
)

from .event_discovery_catalog import (
    TAIPEI_TZ,
    _catalog_content,
    _history_artifact_path,
    _history_with_files,
    _load_or_create_catalog,
    _normalized_history_index,
    artifact_matches,
    iso_seconds,
    load_event_evidence_catalog,
    now_taipei,
    verify_event_evidence_catalog,
)
from .event_discovery_evidence import (
    _capture_evidence,
    _mark_corrupt_evidence,
    _refresh_candidate_collection,
    _safe_failure_reason,
)
from .event_discovery_metrics import (
    apply_trigger_metrics,
    expected_data_times,
    metric_from_frame as _metric_from_frame,
    scan_files as _scan_files,
)
from .event_discovery_types import (
    EventDiscoveryResult,
    FileHttpGet,
    FrameHttpGet,
    HistoryHttpGet,
)

PIPELINE_NAME = "event_discover"
CATALOG_NAME = "event_evidence_catalog.json"
DEFAULT_CACHE_RETENTION_HOURS = 48.0
DEFAULT_CACHE_MAX_BYTES = 10 * 1024 * 1024 * 1024
LOGGER = logging.getLogger(__name__)

__all__ = [
    "EventDiscoveryResult",
    "FileHttpGet",
    "FrameHttpGet",
    "HistoryHttpGet",
    "apply_trigger_metrics",
    "artifact_matches",
    "expected_data_times",
    "iso_seconds",
    "load_event_evidence_catalog",
    "now_taipei",
    "run_event_discovery",
    "verify_event_evidence_catalog",
]


def _verified_history_get(
    url: str,
    *,
    params: dict[str, str],
    timeout: int,
    verify: bool,
) -> HistoryHttpResponse:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return cast(
        HistoryHttpResponse,
        verified_get(url, params=params, headers=None, timeout=float(timeout)),
    )


def _verified_frame_get(url: str, *, timeout: int, verify: bool) -> FrameHttpResponse:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return cast(
        FrameHttpResponse,
        verified_get(url, params={}, headers=None, timeout=float(timeout)),
    )


def _verified_file_get(
    url: str,
    *,
    params: dict[str, str],
    timeout: int,
    verify: bool,
) -> FileHttpResponse:
    if not verify:
        raise ValueError("event discovery requires TLS verification")
    return cast(
        FileHttpResponse,
        verified_get(url, params=params, headers=None, timeout=float(timeout)),
    )


def _fetch_history_with_retry(
    *,
    config: DiscoveryConfig,
    authorization: str,
    timeout: int,
    retry_attempts: int,
    retry_backoff_seconds: float,
    history_http_get: HistoryHttpGet,
) -> CwaHistoryIndex:
    for attempt in range(1, retry_attempts + 1):
        try:
            return fetch_history_index(
                CwaHistoryRequest(data_id=config.radar_data_id),
                authorization=authorization,
                timeout=timeout,
                http_get=history_http_get,
                verify_tls=True,
            )
        except Exception as exc:
            if attempt == retry_attempts:
                raise RuntimeError(
                    f"CWA history request failed after {attempt} attempts: {type(exc).__name__}"
                ) from exc
            time.sleep(retry_backoff_seconds * (2 ** (attempt - 1)))
    raise AssertionError("CWA history retry loop terminated unexpectedly")


def run_event_discovery(
    *,
    repository_root: Path,
    research_root: Path,
    cwa_api_key: str,
    wra_api_key: str,
    config: DiscoveryConfig,
    county_code: str = "10010",
    county_name: str = "嘉義縣",
    timeout: int = 60,
    max_workers: int = 2,
    retry_attempts: int = 3,
    retry_backoff_seconds: float = 1.0,
    cache_retention_hours: float = DEFAULT_CACHE_RETENTION_HOURS,
    cache_max_bytes: int = DEFAULT_CACHE_MAX_BYTES,
    now: datetime | None = None,
    history_index: CwaHistoryIndex | None = None,
    history_http_get: HistoryHttpGet = _verified_history_get,
    frame_http_get: FrameHttpGet = _verified_frame_get,
    qpe_http_get: FileHttpGet = _verified_file_get,
    gauge_collector: Callable[[], SourceResult] | None = None,
    warning_collector: Callable[[], SourceResult] | None = None,
) -> EventDiscoveryResult:
    if not cwa_api_key:
        raise ValueError("missing CWA_API_KEY")
    if not wra_api_key:
        raise ValueError("missing WRA_API_KEY")
    if timeout <= 0 or max_workers < 1 or retry_attempts < 1:
        raise ValueError("timeout, max_workers, and retry_attempts must be positive")
    current_time = (now or now_taipei()).astimezone(TAIPEI_TZ)
    layout = ResearchLayout(research_root)
    require_external_research_root(layout, repository_root=repository_root)
    layout.ensure()
    catalog_path = layout.discovery / CATALOG_NAME

    with layout.event_discovery_lock():
        catalog, catalog_is_new = _load_or_create_catalog(
            path=catalog_path,
            layout=layout,
            config=config,
            now=current_time,
        )
        original_content = _catalog_content(catalog)
        if history_index is None:
            history_index = _fetch_history_with_retry(
                config=config,
                authorization=cwa_api_key,
                timeout=timeout,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                history_http_get=history_http_get,
            )
        history_index = _normalized_history_index(history_index)
        history_artifacts = {artifact.path: artifact for artifact in catalog.history_indexes}
        scan_files = _scan_files(index=history_index, cursor=catalog.cursor, config=config)
        metrics: list[RadarFrameMetric] = []
        if scan_files:
            scan_index = _history_with_files(history_index, scan_files)
            history_path = _history_artifact_path(layout, scan_index)
            write_schema_if_changed(history_path, scan_index)
            history_artifact = artifact_record(
                layout,
                history_path,
                kind="cwa_incremental_history_index",
            )
            history_artifacts[history_artifact.path] = history_artifact
            first_time = aware_datetime(scan_files[0].data_time, field="scan frame")
            last_time = aware_datetime(scan_files[-1].data_time, field="scan frame")
            scan_id = f"scan_{first_time:%Y%m%dt%H%M}_{last_time:%Y%m%dt%H%M}"
            scan_plan = build_event_plan(
                scan_index.model_dump(mode="json"),
                event_id=scan_id,
                start_time=iso_seconds(first_time),
                end_time=iso_seconds(last_time),
            )
            scan_collection = download_event_frames(
                scan_plan,
                output_dir=layout.discovery_cache,
                authorization=cwa_api_key,
                timeout=timeout,
                http_get=frame_http_get,
                overwrite=True,
                max_workers=max_workers,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
            )
            for frame in scan_collection.frames:
                metric = _metric_from_frame(
                    path=Path(frame.output_path),
                    data_time=frame.data_time,
                    config=config,
                )
                metric_path = layout.discovery_metrics / (
                    f"{aware_datetime(metric.data_time, field='metric'):%Y%m%dT%H%M%S%z}.json"
                )
                write_schema_if_changed(metric_path, metric)
                metrics.append(metric)

        candidates = apply_trigger_metrics(
            catalog.candidates,
            metrics=tuple(metrics),
            config=config,
        )
        latest_history_time = (
            aware_datetime(history_index.files[-1].data_time, field="history latest")
            if history_index.files
            else None
        )
        refreshed = []
        for candidate in candidates:
            candidate = _mark_corrupt_evidence(candidate, layout=layout)
            updated = _refresh_candidate_collection(
                candidate,
                history_index=history_index,
                history_latest=latest_history_time,
                layout=layout,
                authorization=cwa_api_key,
                config=config,
                timeout=timeout,
                max_workers=max_workers,
                retry_attempts=retry_attempts,
                retry_backoff_seconds=retry_backoff_seconds,
                frame_http_get=frame_http_get,
            )
            retry_targets = [
                capture.target_data_time
                for capture in updated.evidence_captures
                if any(
                    source.status == "error"
                    for source in (capture.qpe, capture.gauges, capture.warnings)
                )
            ]
            if not any(
                capture.target_data_time == updated.last_trigger_time
                for capture in updated.evidence_captures
            ):
                retry_targets.append(updated.last_trigger_time)
            for target_data_time in dict.fromkeys(retry_targets):
                gauge_collect = gauge_collector or (
                    lambda: CwaRainGaugeAdapter(
                        authorization=cwa_api_key,
                        county_code=county_code,
                        county_name=county_name,
                        timeout_seconds=float(timeout),
                    ).collect()
                )
                warning_collect = warning_collector or (
                    lambda: WraRainfallAlertAdapter(
                        api_key=wra_api_key,
                        county_code=county_code,
                        timeout_seconds=float(timeout),
                    ).collect()
                )
                updated = _capture_evidence(
                    updated,
                    target_data_time=target_data_time,
                    layout=layout,
                    now=current_time,
                    cwa_api_key=cwa_api_key,
                    wra_api_key=wra_api_key,
                    county_code=county_code,
                    county_name=county_name,
                    timeout=timeout,
                    retry_attempts=retry_attempts,
                    retry_backoff_seconds=retry_backoff_seconds,
                    qpe_http_get=qpe_http_get,
                    gauge_collector=gauge_collect,
                    warning_collector=warning_collect,
                    max_alignment_minutes=config.evidence_max_alignment_minutes,
                )
            refreshed.append(updated)

        cursor = catalog.cursor
        if metrics:
            cursor = DiscoveryCursor(
                last_scanned_data_time=max(
                    (metric.data_time for metric in metrics),
                    key=lambda value: aware_datetime(value, field="metric"),
                ),
                last_successful_scan_at=iso_seconds(current_time),
            )
        candidate_catalog = EventEvidenceCatalog.model_validate(
            catalog.model_dump(mode="python")
            | {
                "cursor": cursor,
                "history_indexes": tuple(
                    history_artifacts[path] for path in sorted(history_artifacts)
                ),
                "candidates": tuple(refreshed),
            }
        )
        changed = catalog_is_new or _catalog_content(candidate_catalog) != original_content
        verification_errors = verify_event_evidence_catalog(
            candidate_catalog,
            layout=layout,
        )
        if verification_errors:
            raise RuntimeError(
                "event evidence catalog verification failed: " + "; ".join(verification_errors)
            )
        if changed:
            candidate_catalog = EventEvidenceCatalog.model_validate(
                candidate_catalog.model_dump(mode="python")
                | {"updated_at": iso_seconds(current_time)}
            )
            write_schema_if_changed(catalog_path, candidate_catalog)

        removed_files, removed_bytes = prune_cache(
            layout.discovery_cache,
            max_age_seconds=cache_retention_hours * 3600,
            max_bytes=cache_max_bytes,
            now_timestamp=current_time.timestamp(),
        )
        evidence_errors = sum(
            source.status == "error"
            for candidate in candidate_catalog.candidates
            for capture in candidate.evidence_captures
            for source in (capture.qpe, capture.gauges, capture.warnings)
        )
        return EventDiscoveryResult(
            catalog_path=catalog_path,
            catalog_changed=changed,
            scanned_frame_count=len(metrics),
            context_trigger_frame_count=sum(bool(metric.candidate_labels) for metric in metrics),
            trigger_frame_count=sum(
                config.candidate_trigger_label in metric.candidate_labels for metric in metrics
            ),
            candidate_count=len(candidate_catalog.candidates),
            complete_candidate_count=sum(
                candidate.radar_collection.complete for candidate in candidate_catalog.candidates
            ),
            evidence_error_count=evidence_errors,
            cache_files_removed=removed_files,
            cache_bytes_removed=removed_bytes,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Incrementally discover CWA radar events and preserve reviewable evidence.",
    )
    parser.add_argument(
        "--data-root",
        "--research-root",
        dest="data_root",
        type=Path,
        default=None,
        help="external durable data root; --research-root is a temporary compatibility alias",
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--initial-lookback-minutes", type=int, default=120)
    parser.add_argument("--merge-gap-minutes", type=int, default=60)
    parser.add_argument("--before-minutes", type=int, default=60)
    parser.add_argument("--after-minutes", type=int, default=60)
    parser.add_argument("--max-candidate-window-minutes", type=int, default=480)
    parser.add_argument("--evidence-max-alignment-minutes", type=int, default=20)
    parser.add_argument("--event-threshold-dbz", type=float, default=35.0)
    parser.add_argument("--local-radius-pixels", type=int, default=8)
    parser.add_argument("--local-min-pixels", type=int, default=1)
    parser.add_argument("--taiwan-min-pixels", type=int, default=1000)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--max-workers", type=int, default=2)
    parser.add_argument("--retry-attempts", type=int, default=3)
    parser.add_argument("--retry-backoff-seconds", type=float, default=1.0)
    parser.add_argument("--cache-retention-hours", type=float, default=48.0)
    parser.add_argument("--cache-max-bytes", type=int, default=DEFAULT_CACHE_MAX_BYTES)
    parser.add_argument("--county-code", default="10010")
    parser.add_argument("--county-name", default="嘉義縣")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    started_at, start_timer = start_run()
    settings = get_settings()
    data_root = args.data_root or settings.data_root
    try:
        result = run_event_discovery(
            repository_root=args.repository_root,
            research_root=data_root,
            cwa_api_key=settings.cwa_api_key,
            wra_api_key=settings.wra_api_key,
            config=DiscoveryConfig(
                initial_lookback_minutes=args.initial_lookback_minutes,
                merge_gap_minutes=args.merge_gap_minutes,
                before_minutes=args.before_minutes,
                after_minutes=args.after_minutes,
                max_candidate_window_minutes=args.max_candidate_window_minutes,
                event_threshold_dbz=args.event_threshold_dbz,
                local_radius_pixels=args.local_radius_pixels,
                local_min_pixels=args.local_min_pixels,
                taiwan_min_pixels=args.taiwan_min_pixels,
                evidence_max_alignment_minutes=args.evidence_max_alignment_minutes,
            ),
            county_code=args.county_code,
            county_name=args.county_name,
            timeout=args.timeout,
            max_workers=args.max_workers,
            retry_attempts=args.retry_attempts,
            retry_backoff_seconds=args.retry_backoff_seconds,
            cache_retention_hours=args.cache_retention_hours,
            cache_max_bytes=args.cache_max_bytes,
        )
    except Exception as exc:
        summary = build_run_summary(
            pipeline=PIPELINE_NAME,
            status="error",
            failure_reason=_safe_failure_reason(
                exc,
                secrets=(settings.cwa_api_key, settings.wra_api_key),
            ),
            started_at=started_at,
            start_timer=start_timer,
            inputs={"data_root": str(data_root)},
            metadata={"candidate_queue_only": True, "automatic_formal_split_updates": False},
        )
        record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
        LOGGER.exception("event discovery failed")
        raise SystemExit(1) from exc

    status = "needs_review" if result.evidence_error_count else "ok"
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status=status,
        failure_reason=(
            f"{result.evidence_error_count} synchronized evidence sources need retry"
            if result.evidence_error_count
            else ""
        ),
        started_at=started_at,
        start_timer=start_timer,
        inputs={"data_root": str(data_root), "radar_data_id": "O-A0059-001"},
        outputs={"event_evidence_catalog": str(result.catalog_path)},
        row_counts={
            "scanned_frames": result.scanned_frame_count,
            "trigger_frames": result.trigger_frame_count,
            "context_trigger_frames": result.context_trigger_frame_count,
            "candidates": result.candidate_count,
            "complete_candidates": result.complete_candidate_count,
            "evidence_errors": result.evidence_error_count,
            "cache_files_removed": result.cache_files_removed,
            "cache_bytes_removed": result.cache_bytes_removed,
        },
        metadata={
            "catalog_changed": result.catalog_changed,
            "event_threshold_dbz": args.event_threshold_dbz,
            "max_candidate_window_minutes": args.max_candidate_window_minutes,
            "candidate_trigger_label": "minxiong_35dbz",
            "candidate_queue_only": True,
            "automatic_formal_split_updates": False,
            "human_review_required": True,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    LOGGER.info(
        "event discovery complete: scanned=%d candidate_triggers=%d context_triggers=%d "
        "candidates=%d catalog_changed=%s",
        result.scanned_frame_count,
        result.trigger_frame_count,
        result.context_trigger_frame_count,
        result.candidate_count,
        result.catalog_changed,
    )


if __name__ == "__main__":
    main()
