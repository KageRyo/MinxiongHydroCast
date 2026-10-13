from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def validator():
    path = Path(__file__).resolve().parents[1] / "scripts" / "validate_site.py"
    assert path.is_file(), "generated-site link validator is missing"
    spec = spec_from_file_location("validate_site", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_site


def test_valid_site_resolves_subpath_assets_fragments_and_external_links(tmp_path):
    (tmp_path / "guide").mkdir()
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "map.svg").write_text("<svg></svg>")
    (tmp_path / "index.html").write_text(
        '<a href="guide/?q=rain#freshness">Guide</a>'
        '<a href="/MinxiongHydroCast/guide/#freshness">Guide</a>'
        '<a href="https://example.com/missing">External</a>'
        '<a href="mailto:maintainer@example.com">Email</a>'
        '<a href="#">Menu</a><img src="assets/map.svg">'
        '<script src="assets/map.svg"></script>'
    )
    (tmp_path / "guide" / "index.html").write_text(
        '<h1 id="freshness">Freshness</h1><a href="../">Home</a>'
    )
    assert validator()(tmp_path) == []


def test_missing_files_and_anchors_are_reported(tmp_path):
    (tmp_path / "index.html").write_text(
        '<a href="missing/">Missing</a><a href="#absent">Absent</a>'
        '<img src="assets/missing.svg">'
    )
    errors = validator()(tmp_path)
    assert len(errors) == 3
    assert any("missing/" in error for error in errors)
    assert any("#absent" in error for error in errors)
    assert any("assets/missing.svg" in error for error in errors)


def test_relative_escape_and_wrong_root_path_are_reported(tmp_path):
    (tmp_path / "index.html").write_text(
        '<a href="../private.txt">Escape</a><a href="/guide/">Wrong root</a>'
    )
    assert len(validator()(tmp_path)) == 2


def test_percent_encoded_links_and_fragments_resolve(tmp_path):
    (tmp_path / "some page.html").write_text('<h1 id="雨量">Rain</h1>')
    (tmp_path / "index.html").write_text(
        '<a href="some%20page.html#%E9%9B%A8%E9%87%8F">Rain</a>'
    )
    assert validator()(tmp_path) == []


def test_missing_site_is_not_reported_as_valid(tmp_path):
    assert validator()(tmp_path / "missing")
