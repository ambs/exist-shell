"""Tests for shared path validation and command utilities."""

import pytest
from typer.testing import CliRunner

from exist_shell.utils import parse_target, validate_path


# --- validate_path ---

def test_valid_simple_path():
    validate_path("/subdir/doc.xml")


def test_valid_root_path():
    validate_path("/")


def test_valid_path_with_spaces():
    validate_path("/sub dir/my doc.xml")


def test_rejects_dotdot_segment():
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/../other/doc.xml")


def test_rejects_dotdot_in_middle():
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/subdir/../secret.xml")


def test_rejects_single_dot_segment():
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/subdir/./doc.xml")


def test_rejects_null_byte():
    with pytest.raises(ValueError, match="null"):
        validate_path("/doc\x00.xml")


# --- parse_target ---

def test_parse_target_returns_nick_and_path():
    assert parse_target("myapp:/docs/file.xml") == ("myapp", "/docs/file.xml")


def test_parse_target_adds_leading_slash():
    assert parse_target("myapp:docs/file.xml") == ("myapp", "/docs/file.xml")


def test_parse_target_path_required_exits_on_missing(runner: CliRunner):
    from typer import Exit
    with pytest.raises((Exit, SystemExit)):
        parse_target("myapp")


def test_parse_target_path_not_required_defaults_to_root():
    assert parse_target("myapp", path_required=False) == ("myapp", "/")


def test_parse_target_path_not_required_uses_given_path():
    assert parse_target("myapp:/sub", path_required=False) == ("myapp", "/sub")


def test_parse_target_rejects_traversal(runner: CliRunner):
    from typer import Exit
    with pytest.raises((Exit, SystemExit)):
        parse_target("myapp:/../other")
