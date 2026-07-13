"""Event-based train/validation/test split checks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

DEFAULT_MANIFEST = Path("data/samples/event_split_manifest.json")
REQUIRED_SPLITS = ("train", "validation", "test")


def parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class WeatherEvent:
    event_id: str
    name: str
    event_type: str
    region: str
    start_time: str
    end_time: str
    source: str = ""
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WeatherEvent":
        return cls(
            event_id=str(payload.get("event_id", "")),
            name=str(payload.get("name", "")),
            event_type=str(payload.get("event_type", "")),
            region=str(payload.get("region", "")),
            start_time=str(payload.get("start_time", "")),
            end_time=str(payload.get("end_time", "")),
            source=str(payload.get("source", "")),
            notes=str(payload.get("notes", "")),
        )

    def validation_errors(self) -> list[str]:
        errors: list[str] = []
        required = {
            "event_id": self.event_id,
            "name": self.name,
            "event_type": self.event_type,
            "region": self.region,
            "start_time": self.start_time,
            "end_time": self.end_time,
        }
        for field, value in required.items():
            if not value:
                errors.append(f"{self.event_id or '<missing>'}: missing {field}")

        start = parse_iso_datetime(self.start_time)
        end = parse_iso_datetime(self.end_time)
        if self.start_time and start is None:
            errors.append(f"{self.event_id}: invalid start_time")
        if self.end_time and end is None:
            errors.append(f"{self.event_id}: invalid end_time")
        if start and end and end <= start:
            errors.append(f"{self.event_id}: end_time must be after start_time")
        return errors

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "name": self.name,
            "event_type": self.event_type,
            "region": self.region,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "source": self.source,
            "notes": self.notes,
            "errors": self.validation_errors(),
        }


@dataclass(frozen=True)
class EventSplitManifest:
    schema_version: str
    split_strategy: str
    target: str
    events: tuple[WeatherEvent, ...]
    splits: dict[str, tuple[str, ...]]
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EventSplitManifest":
        raw_splits = payload.get("splits", {})
        splits = {
            str(name): tuple(str(event_id) for event_id in event_ids)
            for name, event_ids in raw_splits.items()
        }
        return cls(
            schema_version=str(payload.get("schema_version", "1.0")),
            split_strategy=str(payload.get("split_strategy", "")),
            target=str(payload.get("target", "")),
            events=tuple(WeatherEvent.from_dict(event) for event in payload.get("events", [])),
            splits=splits,
            notes=tuple(str(note) for note in payload.get("notes", [])),
        )

    def check(self) -> dict[str, object]:
        errors: list[str] = []
        warnings: list[str] = []
        event_ids = [event.event_id for event in self.events]
        event_id_set = set(event_ids)

        if self.split_strategy != "event_based":
            errors.append("split_strategy must be event_based")
        if not self.target:
            errors.append("target is required")
        if not self.events:
            errors.append("manifest has no events")

        duplicate_ids = sorted(
            {event_id for event_id in event_ids if event_ids.count(event_id) > 1}
        )
        for event_id in duplicate_ids:
            errors.append(f"duplicate event_id: {event_id}")

        for event in self.events:
            errors.extend(event.validation_errors())

        assigned: dict[str, str] = {}
        for split_name in REQUIRED_SPLITS:
            event_ids_for_split = self.splits.get(split_name, ())
            if not event_ids_for_split:
                errors.append(f"{split_name} split is empty")
            for event_id in event_ids_for_split:
                if event_id not in event_id_set:
                    errors.append(f"{split_name} references unknown event_id: {event_id}")
                previous_split = assigned.get(event_id)
                if previous_split and previous_split != split_name:
                    errors.append(
                        f"event_id {event_id} appears in both {previous_split} and {split_name}"
                    )
                assigned[event_id] = split_name

        unknown_splits = sorted(set(self.splits) - set(REQUIRED_SPLITS))
        for split_name in unknown_splits:
            warnings.append(f"unknown split ignored by checker: {split_name}")

        unassigned = sorted(event_id_set - set(assigned))
        for event_id in unassigned:
            warnings.append(f"event is not assigned to any split: {event_id}")

        split_counts = {
            split_name: len(self.splits.get(split_name, ()))
            for split_name in REQUIRED_SPLITS
        }
        status = "ok" if not errors else "error"
        return {
            "schema_version": self.schema_version,
            "status": status,
            "split_strategy": self.split_strategy,
            "target": self.target,
            "event_count": len(self.events),
            "split_counts": split_counts,
            "events": [event.to_dict() for event in self.events],
            "splits": {name: list(event_ids) for name, event_ids in self.splits.items()},
            "warnings": warnings,
            "errors": errors,
            "notes": list(self.notes),
        }


def load_manifest(path: Path) -> EventSplitManifest:
    return EventSplitManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_check_result(result: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
