from datetime import datetime, timezone
from pathlib import Path

import pytest

from minxionghydrocast import __version__
from minxionghydrocast.operations.deployment import (
    DeploymentMetadataError,
    build_deployment_metadata,
    write_deployment_metadata,
)


def repository_with_version(tmp_path: Path, version: str) -> Path:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "pyproject.toml").write_text(
        "[project]\nname = 'minxiong-hydrocast'\nversion = '" + version + "'\n",
        encoding="utf-8",
    )
    return repository


def test_deployment_metadata_records_verified_installed_identity(tmp_path: Path):
    repository = repository_with_version(tmp_path, __version__)

    payload = build_deployment_metadata(
        repository_root=repository,
        revision="a" * 40,
        distribution_version=__version__,
        installed_at=datetime(2026, 8, 18, 2, 0, tzinfo=timezone.utc),
        python_version="3.13.5",
    )
    output = tmp_path / "runtime" / "config" / "deployment.json"
    write_deployment_metadata(output, payload)

    assert payload == {
        "schema_version": 1,
        "package": "minxiong-hydrocast",
        "version": __version__,
        "source_revision": "a" * 40,
        "installed_at": "2026-08-18T02:00:00+00:00",
        "python_version": "3.13.5",
    }
    assert output.read_text(encoding="utf-8").endswith("\n")


def test_deployment_metadata_rejects_version_mismatch(tmp_path: Path):
    repository = repository_with_version(tmp_path, "9.9.9")

    with pytest.raises(DeploymentMetadataError, match="installed version does not match"):
        build_deployment_metadata(
            repository_root=repository,
            revision="a" * 40,
            distribution_version=__version__,
            installed_at=datetime.now(timezone.utc),
            python_version="3.13.5",
        )
