#!/usr/bin/env python3
"""Validate tracked public manifests without requiring private data assets."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "data/samples/event_split_manifest.json"
DEFAULT_CHECKSUM = REPOSITORY_ROOT / "data/samples/event_split_manifest.json.sha256"

# Keep this validation command usable from a clean source checkout before an editable install.
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from minxionghydrocast.models.dataset_schemas import RadarDatasetManifest  # noqa: E402
from minxionghydrocast.models.event_splits import EventSplitManifest  # noqa: E402


def _expected_checksum(checksum_path: Path, manifest_path: Path) -> str:
    fields = checksum_path.read_text(encoding="utf-8").split()
    if len(fields) != 2:
        raise ValueError(f"checksum file must contain one '<sha256>  <filename>' line: {checksum_path}")
    expected, declared_name = fields
    if declared_name != manifest_path.name:
        raise ValueError(
            "checksum file names a different manifest: "
            f"{declared_name} != {manifest_path.name}"
        )
    if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
        raise ValueError(f"checksum is not a lowercase SHA-256 digest: {checksum_path}")
    return expected


def validate_public_manifest(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    checksum_path: Path = DEFAULT_CHECKSUM,
) -> RadarDatasetManifest:
    """Validate the split schema and its tracked byte-level checksum."""

    expected = _expected_checksum(checksum_path, manifest_path)
    actual = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(
            f"manifest checksum mismatch: {manifest_path} expected={expected} actual={actual}"
        )

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = RadarDatasetManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"manifest schema validation failed: {manifest_path}: {exc}") from exc

    split_result = EventSplitManifest.from_dict(payload).check()
    errors = cast(list[str], split_result["errors"])
    if errors:
        raise ValueError(f"event split validation failed: {manifest_path}: {'; '.join(errors)}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--checksum", type=Path, default=DEFAULT_CHECKSUM)
    args = parser.parse_args()
    manifest = validate_public_manifest(
        manifest_path=args.manifest,
        checksum_path=args.checksum,
    )
    print(
        "[OK] public manifest validated "
        f"schema={manifest.schema_version} events={len(manifest.events)}"
    )


if __name__ == "__main__":
    main()
