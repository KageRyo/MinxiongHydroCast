"""Audit provenance-backed Minxiong flood-event labels."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from floodcastminxiong.io.run_summary import now_taipei_iso
from floodcastminxiong.operations.health import parse_timestamp

REQUIRED_FIELDS = {
    "event_id",
    "township",
    "start_at",
    "end_at",
    "observed_flood",
    "source_type",
    "source_reference",
    "reviewed_by",
    "reviewed_at",
    "confirmed",
}
SOURCE_TYPES = {
    "official_report",
    "operator_report",
    "sensor_confirmed",
    "field_survey",
}


@dataclass(frozen=True)
class LabelCriteria:
    minimum_positive_events: int = 10
    minimum_negative_events: int = 20


def load_manifest(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"label manifest cannot be read: {exc}"]
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        return [], ["label manifest schema_version must be 1"]
    labels = payload.get("labels")
    if not isinstance(labels, list):
        return [], ["label manifest labels must be a list"]
    return labels, []


def audit_labels(
    labels: list[dict[str, Any]],
    *,
    criteria: LabelCriteria,
) -> dict[str, Any]:
    errors: list[str] = []
    confirmed: list[tuple[datetime, datetime, dict[str, Any]]] = []
    event_ids: set[str] = set()
    for index, label in enumerate(labels, start=1):
        prefix = f"label {index}"
        if not isinstance(label, dict):
            errors.append(f"{prefix}: entry must be an object")
            continue
        missing = sorted(REQUIRED_FIELDS - set(label))
        if missing:
            errors.append(f"{prefix}: missing fields: {', '.join(missing)}")
            continue
        event_id = str(label["event_id"]).strip()
        if not event_id:
            errors.append(f"{prefix}: event_id is required")
        elif event_id in event_ids:
            errors.append(f"{prefix}: duplicate event_id: {event_id}")
        event_ids.add(event_id)
        if str(label["township"]).strip() != "民雄鄉":
            errors.append(f"{prefix}: township must be 民雄鄉")
        if not isinstance(label["observed_flood"], bool):
            errors.append(f"{prefix}: observed_flood must be a boolean")
        if label["source_type"] not in SOURCE_TYPES:
            errors.append(f"{prefix}: unsupported source_type")
        if not str(label["source_reference"]).strip():
            errors.append(f"{prefix}: source_reference is required")
        if not str(label["reviewed_by"]).strip():
            errors.append(f"{prefix}: reviewed_by is required")
        if label["confirmed"] is not True:
            errors.append(f"{prefix}: confirmed must be true")
        try:
            start_at = parse_timestamp(str(label["start_at"]))
            end_at = parse_timestamp(str(label["end_at"]))
            parse_timestamp(str(label["reviewed_at"]))
        except ValueError:
            errors.append(f"{prefix}: invalid start_at, end_at, or reviewed_at")
            continue
        if end_at <= start_at:
            errors.append(f"{prefix}: end_at must be after start_at")
            continue
        if label["confirmed"] is True:
            confirmed.append((start_at, end_at, label))

    confirmed.sort(key=lambda item: item[0])
    for previous, current in zip(confirmed, confirmed[1:]):
        if current[0] < previous[1]:
            errors.append(
                "confirmed event windows overlap: "
                f"{previous[2]['event_id']} and {current[2]['event_id']}"
            )

    positives = sum(label[2].get("observed_flood") is True for label in confirmed)
    negatives = sum(label[2].get("observed_flood") is False for label in confirmed)
    checks = {
        "valid_manifest": not errors,
        "positive_events": positives >= criteria.minimum_positive_events,
        "negative_events": negatives >= criteria.minimum_negative_events,
    }
    return {
        "schema_version": 1,
        "generated_at": now_taipei_iso(),
        "criteria": {
            "minimum_positive_events": criteria.minimum_positive_events,
            "minimum_negative_events": criteria.minimum_negative_events,
        },
        "counts": {
            "submitted": len(labels),
            "confirmed": len(confirmed),
            "positive": positives,
            "negative": negatives,
        },
        "checks": checks,
        "errors": errors,
        "training_ready": all(checks.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Minxiong flood-event labels.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-positive-events", type=int, default=10)
    parser.add_argument("--minimum-negative-events", type=int, default=20)
    parser.add_argument("--require-training-ready", action="store_true")
    args = parser.parse_args()
    labels, load_errors = load_manifest(args.manifest)
    report = audit_labels(
        labels,
        criteria=LabelCriteria(
            minimum_positive_events=args.minimum_positive_events,
            minimum_negative_events=args.minimum_negative_events,
        ),
    )
    report["errors"] = [*load_errors, *report["errors"]]
    if load_errors:
        report["checks"]["valid_manifest"] = False
        report["training_ready"] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[OK] labels={report['counts']['confirmed']} "
        f"training_ready={report['training_ready']}"
    )
    if report["errors"] or (args.require_training_ready and not report["training_ready"]):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
