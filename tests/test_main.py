"""Tests for the `cli()` entry-point wrapper in main.py."""

import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

import exist_shell.main as main_module
from exist_shell import __version__


def test_cli_converts_keyboard_interrupt_to_exit_130():
    """CLI converts keyboard interrupt to exit 130."""
    with patch.object(main_module, "app", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as exc_info:
            main_module.cli()
    assert exc_info.value.code == 130


def test_version_flag_prints_version_and_exits(runner: CliRunner):
    """Version flag prints version and exits."""
    result = runner.invoke(main_module.app, ["--version"])
    assert result.exit_code == 0
    assert f"exsh {__version__}" in result.output


def test_config_option_overrides_app_state_path(runner: CliRunner, tmp_path: Path):
    """Config option overrides app state path."""
    cfg_path = tmp_path / "custom.toml"
    with patch.object(main_module.app_state, "set_config_path") as mock_set:
        result = runner.invoke(main_module.app, ["--config", str(cfg_path), "server", "--help"])
    assert result.exit_code == 0
    mock_set.assert_called_once_with(cfg_path)


def test_module_entrypoint_invokes_cli_and_shows_help(monkeypatch: pytest.MonkeyPatch):
    """Module entrypoint invokes cli and shows help."""
    monkeypatch.delitem(sys.modules, "exist_shell.main", raising=False)
    with patch.object(sys, "argv", ["exsh", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_module("exist_shell.main", run_name="__main__")
    assert exc_info.value.code == 0
