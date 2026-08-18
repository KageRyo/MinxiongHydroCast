"""Write and validate private deployment metadata after installation."""

from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Callable

from minxionghydrocast import __version__

PACKAGE_NAME = "minxiong-hydrocast"
METADATA_SCHEMA_VERSION = 1


class DeploymentMetadataError(RuntimeError):
    """Raised when an installed deployment cannot be identified unambiguously."""


def expected_project_version(repository_root: Path) -> str:
    import tomllib

    payload = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def build_deployment_metadata(
    *,
    repository_root: Path,
    revision: str,
    distribution_version: str,
    installed_at: datetime,
    python_version: str,
) -> dict[str, object]:
    expected_version = expected_project_version(repository_root)
    versions = {
        "pyproject": expected_version,
        "package": __version__,
        "distribution": distribution_version,
    }
    if len(set(versions.values())) != 1:
        details = ", ".join(f"{name}={value}" for name, value in versions.items())
        raise DeploymentMetadataError(f"installed version does not match source metadata: {details}")
    if not revision or revision.strip() != revision:
        raise DeploymentMetadataError("source revision must be a non-empty trimmed value")
    if installed_at.tzinfo is None:
        raise DeploymentMetadataError("installed_at must include timezone information")
    return {
        "schema_version": METADATA_SCHEMA_VERSION,
        "package": PACKAGE_NAME,
        "version": expected_version,
        "source_revision": revision,
        "installed_at": installed_at.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "python_version": python_version,
    }


def write_deployment_metadata(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(
    argv: list[str] | None = None,
    *,
    distribution_version: Callable[[str], str] = metadata.version,
) -> None:
    parser = argparse.ArgumentParser(
        description="Write verified private metadata for an installed MinxiongHydroCast runtime."
    )
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    payload = build_deployment_metadata(
        repository_root=args.repository_root.resolve(),
        revision=args.revision,
        distribution_version=distribution_version(PACKAGE_NAME),
        installed_at=datetime.now(timezone.utc),
        python_version=platform.python_version(),
    )
    write_deployment_metadata(args.output, payload)


if __name__ == "__main__":
    main()
