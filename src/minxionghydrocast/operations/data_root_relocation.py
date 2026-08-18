"""Safely relocate external data-root metadata after its files have been copied or moved."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from minxionghydrocast.ingestion.cwa_event_collector import CwaEventCollection
from minxionghydrocast.io.data_store import (
    DataLayout,
    atomic_write_bytes,
    canonical_json_bytes,
    require_external_data_root,
    sha256_file,
)
from minxionghydrocast.models.dataset_schemas import DatasetCatalog
from minxionghydrocast.models.event_evidence_schemas import EventEvidenceCatalog
from minxionghydrocast.pipelines.dataset_build import build_dataset_verification_report

DATASET_CATALOG = Path("catalog/dataset_catalog.json")
DATASET_VERIFICATION = Path("catalog/dataset_verification.json")
EVENT_EVIDENCE_CATALOG = Path("discovery/event_evidence_catalog.json")
COLLECTION_FIELDS = {"event_id", "data_id", "frame_count", "bytes_written", "frames"}
ARTIFACT_FIELDS = {"kind", "path", "sha256", "bytes"}


class DataRootRelocationError(ValueError):
    """Raised when a relocation cannot be proven safe before any write occurs."""


@dataclass(frozen=True)
class DocumentChange:
    path: Path
    before: bytes | None
    after: bytes


@dataclass(frozen=True)
class RelocationPlan:
    old_root: Path
    new_root: Path
    changes: tuple[DocumentChange, ...]
    collection_documents: int
    collection_frame_paths: int
    catalog_documents: int
    refreshed_artifact_checksums: int

    def summary(self) -> dict[str, object]:
        return {
            "old_root": str(self.old_root),
            "new_root": str(self.new_root),
            "documents_to_write": [str(change.path) for change in self.changes],
            "collection_documents": self.collection_documents,
            "collection_frame_paths": self.collection_frame_paths,
            "catalog_documents": self.catalog_documents,
            "refreshed_artifact_checksums": self.refreshed_artifact_checksums,
        }


def _normalized_root(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _mapped_output_path(value: str, *, old_root: Path, new_root: Path) -> Path | None:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return None
    normalized = candidate.resolve(strict=False)
    if not _path_is_within(normalized, old_root):
        return None
    return new_root / normalized.relative_to(old_root)


def _change_for_collection(
    path: Path,
    *,
    old_root: Path,
    new_root: Path,
) -> tuple[DocumentChange | None, int]:
    before = path.read_bytes()
    try:
        raw = json.loads(before)
    except json.JSONDecodeError as exc:
        raise DataRootRelocationError(f"invalid JSON in event document: {path}") from exc
    if not isinstance(raw, dict) or not COLLECTION_FIELDS.issubset(raw):
        return None, 0
    try:
        collection = CwaEventCollection.model_validate_json(before)
    except ValidationError as exc:
        raise DataRootRelocationError(f"invalid event collection: {path}: {exc}") from exc

    changed_paths = 0
    frames = []
    for frame in collection.frames:
        mapped = _mapped_output_path(frame.output_path, old_root=old_root, new_root=new_root)
        if mapped is None:
            frames.append(frame)
            continue
        frames.append(frame.model_copy(update={"output_path": str(mapped)}))
        changed_paths += 1
    if not changed_paths:
        return None, 0
    updated = collection.model_copy(update={"frames": tuple(frames)})
    return DocumentChange(path=path, before=before, after=canonical_json_bytes(updated.model_dump())), changed_paths


def _artifact_actual_values(
    path: Path,
    *,
    overrides: dict[Path, bytes],
) -> tuple[str, int]:
    override = overrides.get(path)
    if override is not None:
        return hashlib.sha256(override).hexdigest(), len(override)
    return sha256_file(path), path.stat().st_size


def _refresh_artifact_records(
    value: Any,
    *,
    layout: DataLayout,
    changed_collections: dict[Path, bytes],
    refresh_artifact_checksums: bool,
    errors: list[str],
) -> int:
    """Reconcile staged collection documents with every nested ArtifactRecord in a catalog."""

    refreshed = 0
    if isinstance(value, dict):
        if ARTIFACT_FIELDS.issubset(value):
            if value["kind"] == "tracked_dataset_manifest":
                return 0
            try:
                path = layout.resolve_relative(str(value["path"])).resolve()
            except ValueError as exc:
                errors.append(str(exc))
                return 0
            if not path.is_file():
                errors.append(f"missing artifact: {value['path']}")
                return 0
            actual_sha256, actual_bytes = _artifact_actual_values(
                path,
                overrides=changed_collections,
            )
            if actual_sha256 == value["sha256"] and actual_bytes == value["bytes"]:
                return 0
            if path not in changed_collections and not refresh_artifact_checksums:
                errors.append(
                    "artifact checksum mismatch not caused by a rewritten collection: "
                    f"{value['path']}; inspect it or rerun with --refresh-artifact-checksums"
                )
                return 0
            value["sha256"] = actual_sha256
            value["bytes"] = actual_bytes
            return 1
        for child in value.values():
            refreshed += _refresh_artifact_records(
                child,
                layout=layout,
                changed_collections=changed_collections,
                refresh_artifact_checksums=refresh_artifact_checksums,
                errors=errors,
            )
    elif isinstance(value, list):
        for child in value:
            refreshed += _refresh_artifact_records(
                child,
                layout=layout,
                changed_collections=changed_collections,
                refresh_artifact_checksums=refresh_artifact_checksums,
                errors=errors,
            )
    return refreshed


def _stage_catalog(
    path: Path,
    *,
    catalog_type: type[DatasetCatalog] | type[EventEvidenceCatalog],
    old_root: Path,
    new_root: Path,
    layout: DataLayout,
    changed_collections: dict[Path, bytes],
    refresh_artifact_checksums: bool,
    errors: list[str],
) -> tuple[BaseModel, DocumentChange | None, int]:
    before = path.read_bytes()
    try:
        catalog = catalog_type.model_validate_json(before)
    except ValidationError as exc:
        raise DataRootRelocationError(f"invalid catalog: {path}: {exc}") from exc
    catalog_root = _normalized_root(Path(catalog.data_root))
    if catalog_root not in {old_root, new_root}:
        raise DataRootRelocationError(
            f"catalog data_root does not match --old-root or --new-root: {path} ({catalog.data_root})"
        )

    payload = catalog.model_dump(mode="json")
    payload["data_root"] = str(new_root)
    refreshed = _refresh_artifact_records(
        payload,
        layout=layout,
        changed_collections=changed_collections,
        refresh_artifact_checksums=refresh_artifact_checksums,
        errors=errors,
    )
    try:
        updated = catalog_type.model_validate_json(canonical_json_bytes(payload))
    except ValidationError as exc:
        raise DataRootRelocationError(f"relocated catalog is invalid: {path}: {exc}") from exc
    after = canonical_json_bytes(updated.model_dump(mode="json"))
    change = DocumentChange(path=path, before=before, after=after) if after != before else None
    return updated, change, refreshed


def _append_change(changes: dict[Path, DocumentChange], change: DocumentChange | None) -> None:
    if change is not None:
        changes[change.path] = change


def plan_data_root_relocation(
    *,
    old_root: Path,
    new_root: Path,
    repository_root: Path,
    refresh_artifact_checksums: bool = False,
) -> RelocationPlan:
    """Prepare all metadata updates needed after data files already reside at ``new_root``."""

    old = _normalized_root(old_root)
    new = _normalized_root(new_root)
    repository = _normalized_root(repository_root)
    if old == new:
        raise DataRootRelocationError("--old-root and --new-root must differ")
    if not new.is_dir():
        raise DataRootRelocationError(f"new data root does not exist or is not a directory: {new}")
    layout = DataLayout(new)
    try:
        require_external_data_root(layout, repository_root=repository)
    except ValueError as exc:
        raise DataRootRelocationError(str(exc)) from exc

    changes: dict[Path, DocumentChange] = {}
    collection_documents = 0
    collection_frame_paths = 0
    changed_collections: dict[Path, bytes] = {}
    if layout.events.is_dir():
        for path in sorted(layout.events.rglob("*.json")):
            change, changed_paths = _change_for_collection(path, old_root=old, new_root=new)
            if change is None:
                continue
            _append_change(changes, change)
            changed_collections[path.resolve()] = change.after
            collection_documents += 1
            collection_frame_paths += changed_paths

    errors: list[str] = []
    refreshed_artifact_checksums = 0
    catalog_documents = 0
    dataset_catalog: DatasetCatalog | None = None
    dataset_change: DocumentChange | None = None
    for relative_path, catalog_type in (
        (DATASET_CATALOG, DatasetCatalog),
        (EVENT_EVIDENCE_CATALOG, EventEvidenceCatalog),
    ):
        path = new / relative_path
        if not path.is_file():
            continue
        catalog, change, refreshed = _stage_catalog(
            path,
            catalog_type=catalog_type,
            old_root=old,
            new_root=new,
            layout=layout,
            changed_collections=changed_collections,
            refresh_artifact_checksums=refresh_artifact_checksums,
            errors=errors,
        )
        _append_change(changes, change)
        if change is not None:
            catalog_documents += 1
        refreshed_artifact_checksums += refreshed
        if relative_path == DATASET_CATALOG:
            dataset_catalog = catalog  # type: ignore[assignment]
            dataset_change = change

    if errors:
        raise DataRootRelocationError("data-root relocation preflight failed:\n- " + "\n- ".join(errors))

    if dataset_catalog is not None and dataset_change is not None:
        report = build_dataset_verification_report(
            catalog=dataset_catalog,
            catalog_path=new / DATASET_CATALOG,
            repository_root=repository,
            catalog_bytes=dataset_change.after,
            artifact_bytes_overrides=changed_collections,
        )
        if report.status != "ok":
            raise DataRootRelocationError(
                "data-root relocation verification failed:\n- " + "\n- ".join(report.mismatches)
            )
        verification_path = new / DATASET_VERIFICATION
        before = verification_path.read_bytes() if verification_path.is_file() else None
        after = canonical_json_bytes(report.model_dump(mode="json"))
        if before != after:
            _append_change(
                changes,
                DocumentChange(path=verification_path, before=before, after=after),
            )

    return RelocationPlan(
        old_root=old,
        new_root=new,
        changes=tuple(changes[path] for path in sorted(changes)),
        collection_documents=collection_documents,
        collection_frame_paths=collection_frame_paths,
        catalog_documents=catalog_documents,
        refreshed_artifact_checksums=refreshed_artifact_checksums,
    )


def _backup_path(*, backup_dir: Path, data_root: Path, document: Path) -> Path:
    try:
        return backup_dir / document.relative_to(data_root)
    except ValueError as exc:
        raise DataRootRelocationError(f"document escapes data root: {document}") from exc


def apply_data_root_relocation(
    plan: RelocationPlan,
    *,
    backup_dir: Path | None = None,
) -> Path | None:
    """Back up and atomically write a preflighted relocation plan.

    If an individual replacement fails, previously written documents are restored from memory.
    Data payloads are never moved, copied, or deleted by this command.
    """

    if not plan.changes:
        return None
    default_backup = (
        plan.new_root
        / "migration_backups"
        / f"data_root_relocation_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:8]}"
    )
    destination = _normalized_root(backup_dir or default_backup)
    if not _path_is_within(destination, plan.new_root):
        raise DataRootRelocationError("backup directory must be inside the new data root")
    if destination.exists():
        raise DataRootRelocationError(f"backup directory already exists: {destination}")

    manifest = {
        "operation": "data_root_relocation",
        "old_root": str(plan.old_root),
        "new_root": str(plan.new_root),
        "documents": [
            {
                "path": str(change.path.relative_to(plan.new_root)),
                "created": change.before is None,
            }
            for change in plan.changes
        ],
    }
    for change in plan.changes:
        if change.before is not None:
            atomic_write_bytes(
                _backup_path(
                    backup_dir=destination,
                    data_root=plan.new_root,
                    document=change.path,
                ),
                change.before,
            )
    atomic_write_bytes(destination / "manifest.json", canonical_json_bytes(manifest))

    written: list[DocumentChange] = []
    try:
        for change in plan.changes:
            atomic_write_bytes(change.path, change.after)
            written.append(change)
    except Exception:
        for change in reversed(written):
            if change.before is None:
                change.path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(change.path, change.before)
        raise
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Rewrite checksummed data-root metadata after data files have been copied or moved. "
            "The default is a no-write preflight."
        )
    )
    parser.add_argument("--old-root", type=Path, required=True)
    parser.add_argument("--new-root", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--refresh-artifact-checksums",
        action="store_true",
        help="also accept existing checksum mismatches not caused by rewritten collection manifests",
    )
    parser.add_argument("--apply", action="store_true", help="write the preflighted changes")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="backup location inside --new-root; created only with --apply",
    )
    args = parser.parse_args()

    try:
        plan = plan_data_root_relocation(
            old_root=args.old_root,
            new_root=args.new_root,
            repository_root=args.repository_root,
            refresh_artifact_checksums=args.refresh_artifact_checksums,
        )
        result = plan.summary()
        result["mode"] = "apply" if args.apply else "dry_run"
        if args.apply:
            backup = apply_data_root_relocation(plan, backup_dir=args.backup_dir)
            result["backup_dir"] = str(backup) if backup is not None else None
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except DataRootRelocationError as exc:
        print(f"data-root relocation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
