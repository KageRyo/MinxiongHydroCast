import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from minxionghydrocast import cli


def test_command_mapping_matches_console_scripts():
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    prefix = "minxiong-hydrocast-"
    expected = {
        name.removeprefix(prefix): target
        for name, target in pyproject["project"]["scripts"].items()
        if name.startswith(prefix)
    }

    assert cli.COMMANDS == expected


def test_help_lists_commands_and_aliases(capsys):
    cli.main([])

    output = capsys.readouterr().out
    assert "usage: mhc <command> [args]" in output
    assert "  operations" in output
    assert "  serve" in output
    assert "  collect -> operations" in output


def test_dispatches_alias_and_restores_argv(monkeypatch):
    received: list[str] = []
    original = ["pytest", "original"]
    monkeypatch.setattr(sys, "argv", original)
    monkeypatch.setattr(
        cli,
        "import_module",
        lambda _name: SimpleNamespace(main=lambda: received.extend(sys.argv)),
    )

    cli.main(["collect", "--once"])

    assert received == ["mhc collect", "--once"]
    assert sys.argv is original


def test_unknown_command_exits_with_usage_hint(capsys):
    with pytest.raises(SystemExit, match="2"):
        cli.main(["unknown"])

    error = capsys.readouterr().err
    assert "unknown command: unknown" in error
    assert "mhc --help" in error
