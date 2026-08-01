import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from minxionghydrocast import cli


def test_wheel_exposes_only_single_mhc_console_script():
    pyproject = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())

    assert pyproject["project"]["scripts"] == {"mhc": "minxionghydrocast.cli:main"}
    assert ("collect",) in cli.COMMANDS
    assert ("dataset", "build") in cli.COMMANDS
    assert ("event", "review") in cli.COMMANDS
    assert ("model", "evaluate") in cli.COMMANDS
    assert ("operations", "backup") in cli.COMMANDS


def test_help_lists_grouped_workflows(capsys):
    cli.main([])

    output = capsys.readouterr().out
    assert "usage: mhc <command> [args]" in output
    assert "  collect" in output
    assert "  serve" in output
    assert "  dataset <command>" in output
    assert "mhc operations backup --help" in output


def test_group_help_lists_only_group_commands(capsys):
    cli.main(["event", "--help"])

    output = capsys.readouterr().out
    assert "usage: mhc event <command> [args]" in output
    assert "  discover" in output
    assert "  queue" in output
    assert "  review" in output


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


def test_dispatches_nested_command_and_restores_argv(monkeypatch):
    received: list[str] = []
    original = ["pytest", "original"]
    monkeypatch.setattr(sys, "argv", original)
    monkeypatch.setattr(
        cli,
        "import_module",
        lambda _name: SimpleNamespace(main=lambda: received.extend(sys.argv)),
    )

    cli.main(["dataset", "build", "--dry-run"])

    assert received == ["mhc dataset build", "--dry-run"]
    assert sys.argv is original


def test_unknown_command_exits_with_usage_hint(capsys):
    with pytest.raises(SystemExit, match="2"):
        cli.main(["unknown"])

    error = capsys.readouterr().err
    assert "unknown command: unknown" in error
    assert "mhc --help" in error
