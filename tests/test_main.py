"""Tests for main.py: the `cli()` entry-point wrapper and the registered command tree."""

import re
import runpy
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
import typer.core
import typer.main
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


# ---------------------------------------------------------------------------
# Shell-completion wiring guard
# ---------------------------------------------------------------------------

# A remote-path marker in a param's help text: ``<nick>:<path>`` or ``<nick>[:<path>]``.
# Anchoring on help text is the contract: a remote-target param whose help omits
# the marker is invisible to the guard, so new remote params must document it.
_REMOTE_MARKER = re.compile(r"<nick>\s*\[?:")


def _iter_commands(
    group: typer.core.TyperGroup, path: tuple[str, ...] = ("exsh",)
) -> Iterator[tuple[tuple[str, ...], typer.core.TyperCommand]]:
    """Yield ``(path, command)`` for every leaf command below ``group``, recursing into sub-groups.

    Args:
        group: The group whose registered commands are walked.
        path: Command-name path leading to ``group``.

    Yields:
        The full command path and the command itself, hidden commands included.
    """
    for name, command in group.commands.items():
        if isinstance(command, typer.core.TyperGroup):
            yield from _iter_commands(command, (*path, name))
        elif isinstance(command, typer.core.TyperCommand):
            yield (*path, name), command


def _remote_params(group: typer.core.TyperGroup) -> Iterator[tuple[str, bool]]:
    """Yield ``(label, has_autocompletion)`` for every param whose help carries a remote-path marker.

    Args:
        group: Root group of the command tree to inspect.

    Yields:
        A label such as ``exsh exec --resource`` and whether a completer is wired.
    """
    for path, command in _iter_commands(group):
        for param in command.params:
            if not isinstance(param, (typer.core.TyperArgument, typer.core.TyperOption)):
                continue
            if _REMOTE_MARKER.search(param.help or ""):
                # `_custom_shell_complete` is what Typer sets from `autocompletion=`.
                wired = param._custom_shell_complete is not None
                yield f"{' '.join(path)} {param.opts[0]}", wired


def _no_candidates(incomplete: str) -> list[str]:
    """Return no completions; stands in for a real completer in the probe app."""
    return []


def _build_probe_app() -> typer.Typer:
    """Build a tiny app mixing wired, unwired and non-remote params, one of them in a sub-app."""
    probe = typer.Typer()
    nested = typer.Typer()

    @probe.command("wired")
    def wired(
        target: str = typer.Argument(help="Path: <nick>:<path>.", autocompletion=_no_candidates),
    ) -> None:
        """Wired remote argument."""

    @probe.command("unwired")
    def unwired(
        target: str = typer.Argument(help="Path: <nick>:<path>."),
        yes: bool = typer.Option(False, "--yes", help="Skip the prompt."),
    ) -> None:
        """Unwired remote argument next to a non-remote option."""

    @nested.command("deep")
    def deep(
        resource: str | None = typer.Option(None, "--resource", help="Stored query: <nick>[:<path>]."),
    ) -> None:
        """Unwired remote option inside a sub-app."""

    probe.add_typer(nested, name="nested")
    return probe


def test_remote_target_params_have_autocompletion():
    """Every argument/option documented as `<nick>:<path>` declares an autocompletion callback."""
    missing = [label for label, wired in _remote_params(typer.main.get_group(main_module.app)) if not wired]
    assert not missing, (
        "Remote-target params without `autocompletion=` (add "
        "`collection_target_completer(...)` from exist_shell.completions): " + ", ".join(missing)
    )


def test_remote_target_guard_is_not_vacuous():
    """The guard finds the real remote-target params, so an empty result can't pass silently."""
    labels = {label for label, _ in _remote_params(typer.main.get_group(main_module.app))}
    assert {"exsh ls target", "exsh exec target", "exsh exec --resource", "exsh sync dest"} <= labels


def test_remote_target_guard_flags_missing_autocompletion():
    """The guard reports unwired remote params (even in sub-apps) and ignores wired and non-remote ones."""
    found = dict(_remote_params(typer.main.get_group(_build_probe_app())))
    assert found == {
        "exsh wired target": True,
        "exsh unwired target": False,
        "exsh nested deep --resource": False,
    }
