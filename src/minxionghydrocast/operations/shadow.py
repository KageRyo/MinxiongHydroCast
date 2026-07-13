"""Audit shadow-deployment evidence before notification work can proceed."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from minxionghydrocast.operations.collector import DEFAULT_STORE
from minxionghydrocast.operations.health import parse_timestamp
from minxionghydrocast.operations.snapshot_store import SnapshotStore

TAIPEI_TZ = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class ShadowCriteria:
    lookback_hours: float = 192
    minimum_duration_hours: float = 168
    minimum_live_attempts: int = 900
    minimum_success_rate: float = 0.99
    minimum_readiness_rate: float = 0.95
    maximum_gap_minutes: float = 30
    required_heavy_rain_periods: int = 1


def load_evidence(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    if not path.exists():
        return [], [f"shadow evidence file is missing: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"shadow evidence cannot be read: {exc}"]
    periods = payload.get("heavy_rain_periods") if isinstance(payload, dict) else None
    if not isinstance(periods, list):
        return [], ["shadow evidence heavy_rain_periods must be a list"]
    confirmed: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, period in enumerate(periods, start=1):
        if not isinstance(period, dict):
            errors.append(f"evidence {index}: entry must be an object")
            continue
        required = {"event_id", "start_at", "end_at", "source", "reviewed_by", "confirmed"}
        missing = sorted(required - set(period))
        if missing:
            errors.append(f"evidence {index}: missing fields: {', '.join(missing)}")
            continue
        if period.get("confirmed") is not True:
            continue
        try:
            start_at = parse_timestamp(str(period["start_at"]))
            end_at = parse_timestamp(str(period["end_at"]))
        except ValueError:
            errors.append(f"evidence {index}: invalid start_at or end_at")
            continue
        if end_at <= start_at:
            errors.append(f"evidence {index}: end_at must be after start_at")
            continue
        if not str(period["source"]).strip() or not str(period["reviewed_by"]).strip():
            errors.append(f"evidence {index}: source and reviewed_by are required")
            continue
        confirmed.append({**period, "_start": start_at, "_end": end_at})
    return confirmed, errors


def _rates(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def evaluate_shadow(
    store: SnapshotStore,
    *,
    evidence_path: Path,
    criteria: ShadowCriteria,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(TAIPEI_TZ)
    cutoff = now - timedelta(hours=criteria.lookback_hours)
    manifests, storage_errors = store.scan_manifests()
    attempts: list[tuple[datetime, dict[str, Any]]] = []
    manifest_errors = list(storage_errors)
    for manifest in manifests:
        try:
            completed_at = parse_timestamp(str(manifest["completed_at"]))
        except (KeyError, ValueError):
            manifest_errors.append(
                f"{manifest.get('snapshot_id', 'unknown')}: invalid completed_at"
            )
            continue
        if cutoff <= completed_at <= now and manifest.get("mode") == "live":
            attempts.append((completed_at, manifest))
    attempts.sort(key=lambda item: item[0])

    successful = [item for item in attempts if item[1].get("status") == "ok"]
    ready: list[tuple[datetime, dict[str, Any]]] = []
    for item in successful:
        integrity_errors = store.verify_snapshot(item[1])
        if integrity_errors:
            manifest_errors.extend(
                f"{item[1].get('snapshot_id', 'unknown')}: {error}" for error in integrity_errors
            )
            continue
        if item[1].get("health", {}).get("ready") is True:
            ready.append(item)

    duration_hours = 0.0
    if len(attempts) >= 2:
        duration_hours = (attempts[-1][0] - attempts[0][0]).total_seconds() / 3600
    gap_minutes: list[float] = []
    if ready:
        gap_minutes.extend(
            (current[0] - previous[0]).total_seconds() / 60
            for previous, current in zip(ready, ready[1:])
        )
        gap_minutes.append((now - ready[-1][0]).total_seconds() / 60)
    maximum_gap = max(gap_minutes) if gap_minutes else None

    evidence, evidence_errors = load_evidence(evidence_path)
    covered_evidence = []
    ready_times = [item[0] for item in ready]
    for period in evidence:
        event_times = [
            timestamp
            for timestamp in ready_times
            if period["_start"] <= timestamp <= period["_end"]
        ]
        event_gaps: list[float] = []
        if event_times:
            event_gaps.append((event_times[0] - period["_start"]).total_seconds() / 60)
            event_gaps.extend(
                (current - previous).total_seconds() / 60
                for previous, current in zip(event_times, event_times[1:])
            )
            event_gaps.append((period["_end"] - event_times[-1]).total_seconds() / 60)
        if event_gaps and max(event_gaps) <= criteria.maximum_gap_minutes:
            covered_evidence.append(period)

    attempt_count = len(attempts)
    success_rate = _rates(len(successful), attempt_count)
    readiness_rate = _rates(len(ready), attempt_count)
    reasons = [*manifest_errors, *evidence_errors]
    checks = {
        "duration": duration_hours >= criteria.minimum_duration_hours,
        "live_attempts": attempt_count >= criteria.minimum_live_attempts,
        "success_rate": success_rate >= criteria.minimum_success_rate,
        "readiness_rate": readiness_rate >= criteria.minimum_readiness_rate,
        "maximum_gap": maximum_gap is not None and maximum_gap <= criteria.maximum_gap_minutes,
        "heavy_rain_periods": len(covered_evidence) >= criteria.required_heavy_rain_periods,
        "storage_integrity": not manifest_errors,
        "evidence_valid": not evidence_errors,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    shadow_gate_passed = all(checks.values())
    return {
        "schema_version": 1,
        "evaluated_at": now.isoformat(timespec="seconds"),
        "window": {
            "start_at": cutoff.isoformat(timespec="seconds"),
            "end_at": now.isoformat(timespec="seconds"),
        },
        "criteria": {
            "lookback_hours": criteria.lookback_hours,
            "minimum_duration_hours": criteria.minimum_duration_hours,
            "minimum_live_attempts": criteria.minimum_live_attempts,
            "minimum_success_rate": criteria.minimum_success_rate,
            "minimum_readiness_rate": criteria.minimum_readiness_rate,
            "maximum_gap_minutes": criteria.maximum_gap_minutes,
            "required_heavy_rain_periods": criteria.required_heavy_rain_periods,
        },
        "metrics": {
            "live_attempts": attempt_count,
            "successful_attempts": len(successful),
            "ready_attempts": len(ready),
            "duration_hours": round(duration_hours, 3),
            "success_rate": success_rate,
            "readiness_rate": readiness_rate,
            "maximum_gap_minutes": round(maximum_gap, 3) if maximum_gap is not None else None,
            "confirmed_heavy_rain_periods": len(evidence),
            "covered_heavy_rain_periods": len(covered_evidence),
        },
        "checks": checks,
        "shadow_gate_passed": shadow_gate_passed,
        "notification_allowed": False,
        "notification_blockers": sorted(set(reasons))
        + [
            "notification delivery is not implemented and local model-label gates are not satisfied"
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the shadow-deployment gate.")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lookback-hours", type=float, default=192)
    parser.add_argument("--minimum-duration-hours", type=float, default=168)
    parser.add_argument("--minimum-live-attempts", type=int, default=900)
    parser.add_argument("--minimum-success-rate", type=float, default=0.99)
    parser.add_argument("--minimum-readiness-rate", type=float, default=0.95)
    parser.add_argument("--maximum-gap-minutes", type=float, default=30)
    parser.add_argument("--required-heavy-rain-periods", type=int, default=1)
    parser.add_argument(
        "--allow-blocked",
        action="store_true",
        help="Write a blocked report without returning a non-zero scheduler status.",
    )
    args = parser.parse_args()
    report = evaluate_shadow(
        SnapshotStore(args.store),
        evidence_path=args.evidence,
        criteria=ShadowCriteria(
            lookback_hours=args.lookback_hours,
            minimum_duration_hours=args.minimum_duration_hours,
            minimum_live_attempts=args.minimum_live_attempts,
            minimum_success_rate=args.minimum_success_rate,
            minimum_readiness_rate=args.minimum_readiness_rate,
            maximum_gap_minutes=args.maximum_gap_minutes,
            required_heavy_rain_periods=args.required_heavy_rain_periods,
        ),
    )
    store = SnapshotStore(args.store)
    store.write_report("shadow_report.json", report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        f"[OK] Shadow gate passed={report['shadow_gate_passed']} "
        f"notification_allowed={report['notification_allowed']}"
    )
    if not report["shadow_gate_passed"] and not args.allow_blocked:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
