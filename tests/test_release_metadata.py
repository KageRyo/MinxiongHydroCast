import re
import tomllib
from pathlib import Path

from minxionghydrocast import __version__


REPOSITORY_ROOT = Path(__file__).parents[1]


def test_release_metadata_uses_the_package_version():
    pyproject = tomllib.loads((REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    citation = (REPOSITORY_ROOT / "CITATION.cff").read_text(encoding="utf-8")
    changelog = (REPOSITORY_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (
        REPOSITORY_ROOT / "docs" / "releases" / f"v{__version__}.md"
    ).read_text(encoding="utf-8")

    citation_version = re.search(r"^version: (.+)$", citation, flags=re.MULTILINE)

    assert citation_version is not None
    assert pyproject["project"]["version"] == __version__
    assert citation_version.group(1) == __version__
    assert f"## [{__version__}]" in changelog
    assert f"Release tag: `v{__version__}`" in release_notes
