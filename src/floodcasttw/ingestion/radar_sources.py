"""Radar source manifest checks before tensor conversion."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from floodcasttw.io.run_summary import (
    DEFAULT_RUN_LOG_PATH,
    build_run_summary,
    default_run_summary_path,
    record_run,
    start_run,
)

PIPELINE_NAME = "radar_source_check"
DEFAULT_MANIFEST = Path("data/samples/radar_source_manifest.json")

CONFIRMATION_FIELDS = (
    "provider",
    "source_url",
    "license",
    "license_url",
    "access_method",
    "native_format",
    "crs",
    "grid",
    "units",
    "local_path",
)


@dataclass(frozen=True)
class RadarSource:
    name: str
    status: str
    provider: str = ""
    source_url: str = ""
    documentation_url: str = ""
    license: str = ""
    license_url: str = ""
    access_method: str = ""
    native_format: str = ""
    cadence_minutes: int | None = None
    crs: str = ""
    grid: str = ""
    units: str = ""
    spatial_coverage: str = ""
    temporal_coverage: str = ""
    local_path: Path | None = None
    notes: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RadarSource":
        local_path = payload.get("local_path") or None
        cadence = payload.get("cadence_minutes")
        return cls(
            name=str(payload.get("name", "")),
            status=str(payload.get("status", "candidate")),
            provider=str(payload.get("provider", "")),
            source_url=str(payload.get("source_url", "")),
            documentation_url=str(payload.get("documentation_url", "")),
            license=str(payload.get("license", "")),
            license_url=str(payload.get("license_url", "")),
            access_method=str(payload.get("access_method", "")),
            native_format=str(payload.get("native_format", "")),
            cadence_minutes=int(cadence) if cadence not in (None, "") else None,
            crs=str(payload.get("crs", "")),
            grid=str(payload.get("grid", "")),
            units=str(payload.get("units", "")),
            spatial_coverage=str(payload.get("spatial_coverage", "")),
            temporal_coverage=str(payload.get("temporal_coverage", "")),
            local_path=Path(local_path) if local_path else None,
            notes=str(payload.get("notes", "")),
        )

    def missing_confirmation_fields(self) -> list[str]:
        missing = []
        values = self.to_dict(include_exists=False)
        for field in CONFIRMATION_FIELDS:
            value = values.get(field)
            if value in ("", None, "needs_review", "unknown"):
                missing.append(field)
        if not self.cadence_minutes or self.cadence_minutes <= 0:
            missing.append("cadence_minutes")
        return missing

    def local_path_exists(self) -> bool:
        return bool(self.local_path and self.local_path.exists())

    def is_confirmed(self) -> bool:
        return self.status == "confirmed" and not self.missing_confirmation_fields()

    def to_dict(self, *, include_exists: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.name,
            "status": self.status,
            "provider": self.provider,
            "source_url": self.source_url,
            "documentation_url": self.documentation_url,
            "license": self.license,
            "license_url": self.license_url,
            "access_method": self.access_method,
            "native_format": self.native_format,
            "cadence_minutes": self.cadence_minutes,
            "crs": self.crs,
            "grid": self.grid,
            "units": self.units,
            "spatial_coverage": self.spatial_coverage,
            "temporal_coverage": self.temporal_coverage,
            "local_path": str(self.local_path) if self.local_path else "",
            "notes": self.notes,
        }
        if include_exists:
            payload["local_path_exists"] = self.local_path_exists()
            payload["missing_confirmation_fields"] = self.missing_confirmation_fields()
            payload["confirmed"] = self.is_confirmed()
        return payload


@dataclass(frozen=True)
class RadarSourceManifest:
    schema_version: str
    selected_source: str
    sources: tuple[RadarSource, ...]
    review_notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RadarSourceManifest":
        return cls(
            schema_version=str(payload.get("schema_version", "1.0")),
            selected_source=str(payload.get("selected_source", "")),
            sources=tuple(RadarSource.from_dict(source) for source in payload.get("sources", [])),
            review_notes=tuple(str(note) for note in payload.get("review_notes", [])),
        )

    def selected(self) -> RadarSource | None:
        for source in self.sources:
            if source.name == self.selected_source:
                return source
        return None

    def check(self) -> dict[str, object]:
        selected = self.selected()
        source_payloads = [source.to_dict() for source in self.sources]
        errors: list[str] = []
        if not self.sources:
            errors.append("manifest has no sources")
        if self.selected_source and selected is None:
            errors.append(f"selected source not found: {self.selected_source}")
        if selected and not selected.is_confirmed():
            missing = ", ".join(selected.missing_confirmation_fields())
            errors.append(f"selected source is not confirmed: missing {missing}")
        status = "ok" if not errors else "needs_review"
        return {
            "schema_version": self.schema_version,
            "status": status,
            "selected_source": self.selected_source,
            "sources": source_payloads,
            "review_notes": list(self.review_notes),
            "errors": errors,
        }


def load_manifest(path: Path) -> RadarSourceManifest:
    return RadarSourceManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def write_check_result(result: dict[str, object], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Check radar source manifest readiness.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/radar_source_check.json"),
    )
    parser.add_argument("--require-confirmed", action="store_true")
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=default_run_summary_path(PIPELINE_NAME),
    )
    parser.add_argument("--log-output", type=Path, default=DEFAULT_RUN_LOG_PATH)
    args = parser.parse_args()

    started_at, start_timer = start_run()
    manifest = load_manifest(args.manifest)
    result = manifest.check()
    write_check_result(result, args.output)
    summary = build_run_summary(
        pipeline=PIPELINE_NAME,
        status="ok" if result["status"] == "ok" else "needs_review",
        failure_reason="; ".join(result["errors"]),
        started_at=started_at,
        start_timer=start_timer,
        inputs={"manifest": str(args.manifest)},
        outputs={"check_result": str(args.output)},
        row_counts={"sources": len(manifest.sources)},
        metadata={
            "selected_source": result["selected_source"],
            "require_confirmed": args.require_confirmed,
        },
    )
    record_run(summary_output=args.summary_output, log_output=args.log_output, summary=summary)
    print(f"[OK] Wrote radar source check to {args.output}")
    if args.require_confirmed and result["status"] != "ok":
        raise SystemExit("[ERROR] Radar source manifest still needs review.")


if __name__ == "__main__":
    main()
