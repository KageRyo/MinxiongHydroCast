"""Build a read-only incident queue from rolling shadow readiness gaps."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from minxionghydrocast.io.research_store import (
    atomic_write_bytes,
    canonical_json_bytes,
)
from minxionghydrocast.operations.collector import DEFAULT_STORE
from minxionghydrocast.operations.health import parse_timestamp
from minxionghydrocast.operations.snapshot_store import SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")
REPORT_NAME = "shadow_gap_incidents.json"
DERIVED_DATASETS = {"location_reference", "region_features"}


@dataclass(frozen=True)
class GapIncidentCriteria:
    lookback_hours: float = 192
    maximum_gap_minutes: float = 30

    def __post_init__(self) -> None:
        if self.lookback_hours <= 0:
            raise ValueError("lookback_hours must be greater than zero")
        if self.maximum_gap_minutes <= 0:
            raise ValueError("maximum_gap_minutes must be greater than zero")


@dataclass(frozen=True)
class LiveAttempt:
    completed_at: datetime
    manifest: dict[str, Any]
    integrity_errors: tuple[str, ...] = ()

    @property
    def successful(self) -> bool:
        return self.manifest.get("status") == "ok"

    @property
    def readable_snapshot(self) -> bool:
        return self.successful and not self.integrity_errors

    @property
    def ready(self) -> bool:
        return (
            self.readable_snapshot
            and self.manifest.get("health", {}).get("ready") is True
        )


def _scan_live_attempts(
    store: SnapshotStore,
    *,
    cutoff: datetime,
    now: datetime,
) -> tuple[list[LiveAttempt], list[str]]:
    manifests, storage_errors = store.scan_manifests()
    errors = list(storage_errors)
    attempts: list[LiveAttempt] = []
    for manifest in manifests:
        try:
            completed_at = parse_timestamp(str(manifest["completed_at"]))
        except (KeyError, ValueError):
            errors.append(
                f"{manifest.get('snapshot_id', 'unknown')}: invalid completed_at"
            )
            continue
        if not (cutoff <= completed_at <= now) or manifest.get("mode") != "live":
            continue
        integrity_errors = (
            tuple(store.verify_snapshot(manifest))
            if manifest.get("status") == "ok"
            else ()
        )
        errors.extend(
            f"{manifest.get('snapshot_id', 'unknown')}: {error}"
            for error in integrity_errors
        )
        attempts.append(
            LiveAttempt(
                completed_at=completed_at,
                manifest=manifest,
                integrity_errors=integrity_errors,
            )
        )
    attempts.sort(key=lambda attempt: attempt.completed_at)
    return attempts, errors


def _affected_datasets(attempt: LiveAttempt) -> list[dict[str, Any]]:
    affected: list[dict[str, Any]] = []
    datasets = attempt.manifest.get("datasets", {})
    if not isinstance(datasets, dict):
        return affected
    for name, raw_details in sorted(datasets.items()):
        if not isinstance(raw_details, dict):
            continue
        health = raw_details.get("health", {})
        if not isinstance(health, dict) or health.get("ready") is True:
            continue
        source = raw_details.get("source", {})
        if not isinstance(source, dict):
            source = {}
        affected.append(
            {
                "dataset": name,
                "role": "derived" if name in DERIVED_DATASETS else "source",
                "state": health.get("state"),
                "observed_at": health.get("observed_at"),
                "age_minutes": health.get("age_minutes"),
                "max_age_minutes": health.get("max_age_minutes"),
                "authority": source.get("authority"),
                "source_kind": source.get("source_kind"),
                "source_outcome": source.get("outcome"),
            }
        )
    return affected


def _metadata(manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = manifest.get("metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _attempt_evidence(attempt: LiveAttempt) -> dict[str, Any]:
    metadata = _metadata(attempt.manifest)
    return {
        "completed_at": attempt.completed_at.isoformat(timespec="seconds"),
        "snapshot_id": attempt.manifest.get("snapshot_id"),
        "status": attempt.manifest.get("status"),
        "health_state": attempt.manifest.get("health", {}).get("state"),
        "health_ready": attempt.manifest.get("health", {}).get("ready") is True,
        "readable_snapshot": attempt.readable_snapshot,
        "integrity_errors": list(attempt.integrity_errors),
        "failure_kind": metadata.get("failure_kind"),
        "failure_reason": attempt.manifest.get("failure_reason"),
        "source_retries": metadata.get("source_retries", {}),
        "affected_datasets": _affected_datasets(attempt),
    }


def _source_summary(attempts: list[LiveAttempt]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for attempt in attempts:
        for evidence in _affected_datasets(attempt):
            key = (
                str(evidence["dataset"]),
                str(evidence["role"]),
                str(evidence["authority"] or ""),
            )
            summary = grouped.setdefault(
                key,
                {
                    "dataset": evidence["dataset"],
                    "role": evidence["role"],
                    "authority": evidence["authority"],
                    "state_counts": Counter(),
                    "observed_at": [],
                    "maximum_age_minutes": None,
                    "configured_max_age_minutes": evidence["max_age_minutes"],
                },
            )
            summary["state_counts"][str(evidence["state"] or "unknown")] += 1
            if evidence["observed_at"]:
                summary["observed_at"].append(str(evidence["observed_at"]))
            if evidence["age_minutes"] is not None:
                current_maximum = summary["maximum_age_minutes"]
                summary["maximum_age_minutes"] = max(
                    float(evidence["age_minutes"]),
                    float(current_maximum) if current_maximum is not None else 0,
                )

    result: list[dict[str, Any]] = []
    for summary in grouped.values():
        observed_at = sorted(set(summary.pop("observed_at")))
        summary["state_counts"] = dict(sorted(summary["state_counts"].items()))
        summary["first_observed_at"] = observed_at[0] if observed_at else None
        summary["last_observed_at"] = observed_at[-1] if observed_at else None
        if summary["maximum_age_minutes"] is not None:
            summary["maximum_age_minutes"] = round(
                summary["maximum_age_minutes"],
                3,
            )
        result.append(summary)
    return sorted(
        result,
        key=lambda item: (item["role"], item["dataset"], item["authority"] or ""),
    )


def _classify_incident(attempts: list[LiveAttempt]) -> str:
    if not attempts:
        return "no_completed_attempts"
    if any(attempt.integrity_errors for attempt in attempts):
        return "snapshot_integrity_failure"
    successful = [attempt for attempt in attempts if attempt.successful]
    failed = [attempt for attempt in attempts if not attempt.successful]
    upstream_states = {
        str(dataset["state"])
        for attempt in successful
        for dataset in _affected_datasets(attempt)
        if dataset["role"] == "source"
    }
    if successful and not failed and "stale" in upstream_states:
        return "source_data_stale"
    if failed and not successful:
        return "collection_failure"
    if successful and failed:
        return "mixed_collection_and_readiness_failure"
    return "successful_but_not_ready"


def _provisional_root_cause(
    classification: str,
    sources: list[dict[str, Any]],
) -> dict[str, Any]:
    if classification == "source_data_stale":
        stale_sources = [
            source["dataset"]
            for source in sources
            if "stale" in source["state_counts"] and source["role"] == "source"
        ]
        return {
            "status": "evidence_supported_local_cause",
            "summary": (
                "Ready coverage was blocked because source observation timestamps "
                "exceeded their configured freshness limits."
            ),
            "affected_sources": stale_sources,
            "external_cause": None,
        }
    if classification == "no_completed_attempts":
        return {
            "status": "pending_journal_correlation",
            "summary": (
                "No collector attempt completed between the ready boundary snapshots; "
                "service, process, scheduler, and host-resource evidence must be reviewed."
            ),
            "affected_sources": [],
            "external_cause": None,
        }
    if classification == "collection_failure":
        return {
            "status": "evidence_supported_local_cause",
            "summary": "Collection attempts failed before producing a ready snapshot.",
            "affected_sources": [],
            "external_cause": None,
        }
    if classification == "snapshot_integrity_failure":
        return {
            "status": "evidence_supported_local_cause",
            "summary": "Snapshot integrity validation prevented ready coverage.",
            "affected_sources": [],
            "external_cause": None,
        }
    return {
        "status": "pending_review",
        "summary": "The gap contains mixed or unclassified non-ready evidence.",
        "affected_sources": [],
        "external_cause": None,
    }


def _timestamp_id(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S%z")


def _incident_payload(
    previous_ready: LiveAttempt,
    recovery_ready: LiveAttempt | None,
    *,
    end_at: datetime,
    attempts: list[LiveAttempt],
    threshold_minutes: float,
) -> dict[str, Any]:
    duration_minutes = (end_at - previous_ready.completed_at).total_seconds() / 60
    classification = _classify_incident(attempts)
    sources = _source_summary(attempts)
    failed = [attempt for attempt in attempts if not attempt.successful]
    failure_kinds = Counter(
        str(_metadata(attempt.manifest).get("failure_kind") or "unknown")
        for attempt in failed
    )
    return {
        "incident_id": (
            f"gap-{_timestamp_id(previous_ready.completed_at)}-"
            f"{_timestamp_id(end_at) if recovery_ready else 'open'}"
        ),
        "start_at": previous_ready.completed_at.isoformat(timespec="seconds"),
        "end_at": end_at.isoformat(timespec="seconds"),
        "duration_minutes": round(duration_minutes, 3),
        "threshold_minutes": threshold_minutes,
        "open": recovery_ready is None,
        "classification": classification,
        "sources": sources,
        "attempt_count": len(attempts),
        "successful_attempt_count": sum(
            attempt.successful for attempt in attempts
        ),
        "failed_attempt_count": len(failed),
        "readable_snapshot_count": sum(
            attempt.readable_snapshot for attempt in attempts
        ),
        "has_successful_attempt": any(attempt.successful for attempt in attempts),
        "has_readable_snapshot": any(
            attempt.readable_snapshot for attempt in attempts
        ),
        "failure_kind_counts": dict(sorted(failure_kinds.items())),
        "boundary_snapshots": {
            "last_ready": {
                "snapshot_id": previous_ready.manifest.get("snapshot_id"),
                "completed_at": previous_ready.completed_at.isoformat(
                    timespec="seconds"
                ),
            },
            "recovery_ready": (
                {
                    "snapshot_id": recovery_ready.manifest.get("snapshot_id"),
                    "completed_at": recovery_ready.completed_at.isoformat(
                        timespec="seconds"
                    ),
                }
                if recovery_ready
                else None
            ),
        },
        "attempts": [_attempt_evidence(attempt) for attempt in attempts],
        "alert": {
            "triggered": None,
            "evidence": None,
            "status": "not_available_in_snapshot_store",
        },
        "root_cause": _provisional_root_cause(classification, sources),
        "fix": None,
        "reproduced_by_test": None,
        "manual_review": {
            "status": "pending",
            "reviewed_by": None,
            "reviewed_at": None,
            "notes": None,
        },
    }


def build_gap_incident_report(
    store: SnapshotStore,
    *,
    criteria: GapIncidentCriteria,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(TAIPEI_TZ)
    cutoff = now - timedelta(hours=criteria.lookback_hours)
    attempts, storage_errors = _scan_live_attempts(store, cutoff=cutoff, now=now)
    ready = [attempt for attempt in attempts if attempt.ready]

    gap_windows: list[tuple[LiveAttempt, LiveAttempt | None, datetime]] = []
    for previous, current in zip(ready, ready[1:]):
        gap_windows.append((previous, current, current.completed_at))
    if ready:
        gap_windows.append((ready[-1], None, now))

    incidents: list[dict[str, Any]] = []
    measured_gaps: list[float] = []
    for previous, recovery, end_at in gap_windows:
        duration_minutes = (end_at - previous.completed_at).total_seconds() / 60
        measured_gaps.append(duration_minutes)
        if duration_minutes <= criteria.maximum_gap_minutes:
            continue
        during_gap = [
            attempt
            for attempt in attempts
            if previous.completed_at < attempt.completed_at < end_at
        ]
        incidents.append(
            _incident_payload(
                previous,
                recovery,
                end_at=end_at,
                attempts=during_gap,
                threshold_minutes=criteria.maximum_gap_minutes,
            )
        )

    classification_counts = Counter(
        str(incident["classification"]) for incident in incidents
    )
    maximum_gap = max(measured_gaps) if measured_gaps else None
    return {
        "schema_version": 1,
        "evaluated_at": now.isoformat(timespec="seconds"),
        "window": {
            "start_at": cutoff.isoformat(timespec="seconds"),
            "end_at": now.isoformat(timespec="seconds"),
        },
        "criteria": {
            "lookback_hours": criteria.lookback_hours,
            "maximum_gap_minutes": criteria.maximum_gap_minutes,
        },
        "method": {
            "ready_definition": (
                "status=ok, snapshot integrity valid, and aggregate health.ready=true"
            ),
            "gap_definition": (
                "elapsed time between consecutive ready attempts, plus the open tail "
                "from the latest ready attempt to evaluated_at"
            ),
            "window_start_to_first_ready_included": False,
            "history_mutated": False,
            "manual_decisions_automated": False,
        },
        "metrics": {
            "live_attempts": len(attempts),
            "successful_attempts": sum(
                attempt.successful for attempt in attempts
            ),
            "ready_attempts": len(ready),
            "maximum_gap_minutes": (
                round(maximum_gap, 3) if maximum_gap is not None else None
            ),
            "incidents_over_threshold": len(incidents),
            "open_incidents": sum(bool(incident["open"]) for incident in incidents),
            "classification_counts": dict(sorted(classification_counts.items())),
        },
        "storage_errors": storage_errors,
        "manual_review_required": bool(incidents),
        "incidents": incidents,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a read-only incident queue from shadow readiness gaps.",
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lookback-hours", type=float, default=192)
    parser.add_argument("--maximum-gap-minutes", type=float, default=30)
    args = parser.parse_args()

    criteria = GapIncidentCriteria(
        lookback_hours=args.lookback_hours,
        maximum_gap_minutes=args.maximum_gap_minutes,
    )
    store = SnapshotStore(args.store)
    report = build_gap_incident_report(store, criteria=criteria)
    store.write_report(REPORT_NAME, report)
    if args.output:
        atomic_write_bytes(args.output, canonical_json_bytes(report))
    print(
        f"[OK] Gap incidents={report['metrics']['incidents_over_threshold']} "
        f"maximum_gap_minutes={report['metrics']['maximum_gap_minutes']}"
    )


if __name__ == "__main__":
    main()
