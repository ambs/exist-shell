"""Tests for shared path validation utilities."""

import pytest

from exist_shell.utils import validate_path


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
