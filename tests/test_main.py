"""Tests for the `cli()` entry-point wrapper in main.py."""

from unittest.mock import patch

import pytest

import exist_shell.main as main_module


def test_cli_converts_keyboard_interrupt_to_exit_130():
    with patch.object(main_module, "app", side_effect=KeyboardInterrupt):
        with pytest.raises(SystemExit) as exc_info:
            main_module.cli()
    assert exc_info.value.code == 130
