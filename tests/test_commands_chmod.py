"""Tests for the chmod command."""

from unittest.mock import MagicMock, call

import pytest

from exist_shell.commands.chmod import (
    _apply_symbolic_mode,
    _is_octal_mode,
    _parse_octal_mode,
)
from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app
from exist_shell.models import CollectionEntry, ResourceEntry
from pydantic import SecretStr


@pytest.fixture
def client_mock(monkeypatch):
    """Patched ExistClient that returns a mock context-manager."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.chmod.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_with_collection(config_path, a_server):
    """Registered collection 'myapp' on the local server."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))


# ---------------------------------------------------------------------------
# _is_octal_mode
# ---------------------------------------------------------------------------


def test_is_octal_mode_four_digits_with_leading_zero():
    assert _is_octal_mode("0755") is True


def test_is_octal_mode_three_digits():
    assert _is_octal_mode("755") is True


def test_is_octal_mode_one_digit():
    assert _is_octal_mode("7") is True


def test_is_octal_mode_four_digits_no_leading_zero():
    assert _is_octal_mode("4755") is True


def test_is_octal_mode_rejects_invalid_digit():
    assert _is_octal_mode("0888") is False


def test_is_octal_mode_rejects_symbolic():
    assert _is_octal_mode("u+x") is False


def test_is_octal_mode_rejects_empty():
    assert _is_octal_mode("") is False


def test_is_octal_mode_rejects_too_many_digits():
    assert _is_octal_mode("077777") is False


# ---------------------------------------------------------------------------
# _parse_octal_mode
# ---------------------------------------------------------------------------


def test_parse_octal_mode_0755():
    assert _parse_octal_mode("0755") == 0o755


def test_parse_octal_mode_644():
    assert _parse_octal_mode("644") == 0o644


def test_parse_octal_mode_zero():
    assert _parse_octal_mode("0") == 0


def test_parse_octal_mode_4755():
    assert _parse_octal_mode("4755") == 0o4755


# ---------------------------------------------------------------------------
# _apply_symbolic_mode
# ---------------------------------------------------------------------------


def test_symbolic_add_user_execute():
    # rw-r--r-- = 0o644; u+x → rwxr--r-- = 0o744
    assert _apply_symbolic_mode("u+x", 0o644) == 0o744


def test_symbolic_remove_group_other_write():
    # rwxrwxrwx = 0o777; go-w → rwxr-xr-x = 0o755
    assert _apply_symbolic_mode("go-w", 0o777) == 0o755


def test_symbolic_set_all_read_write():
    # 0o755; a=rw → rw-rw-rw- = 0o666
    assert _apply_symbolic_mode("a=rw", 0o755) == 0o666


def test_symbolic_set_user_rwx_group_rx_other_rx():
    # 0o000; u=rwx,go=rx → rwxr-xr-x = 0o755
    assert _apply_symbolic_mode("u=rwx,go=rx", 0o000) == 0o755


def test_symbolic_empty_who_defaults_to_all():
    # =r on 0o777 → r--r--r-- = 0o444
    assert _apply_symbolic_mode("=r", 0o777) == 0o444


def test_symbolic_no_perms_add_is_noop():
    # u+ with no perms: no change
    assert _apply_symbolic_mode("u+", 0o644) == 0o644


def test_symbolic_multiple_clauses():
    # u+x,g-w on rw-rw-rw- = 0o666 → rwx-w-rw- = 0o626... wait
    # 0o666 = rw-rw-rw-; u+x → rwxrw-rw- = 0o766... wait
    # Actually u+x on 0o666: add bit 0o100 → 0o766
    # Then g-w: remove bit 0o020 → 0o746 = rwxr--rw-
    assert _apply_symbolic_mode("u+x,g-w", 0o666) == 0o746


def test_symbolic_setuid():
    # u+s on 0o755 → 0o4755
    assert _apply_symbolic_mode("u+s", 0o755) == 0o4755


def test_symbolic_sticky():
    # o+t on 0o755 → 0o1755
    assert _apply_symbolic_mode("o+t", 0o755) == 0o1755


def test_symbolic_clear_setuid():
    # u-s on 0o4755 → 0o755
    assert _apply_symbolic_mode("u-s", 0o4755) == 0o755


def test_symbolic_equals_clears_special_bits():
    # u=rw on 0o4755 (setuid set): u= clears setuid too → 0o655 (rw-r-xr-x)
    # 0o4755 = rwsr-xr-x; u=rw → rw-r-xr-x = 0o655 (setuid gone)
    assert _apply_symbolic_mode("u=rw", 0o4755) == 0o655


def test_symbolic_raises_on_invalid_clause():
    with pytest.raises(ValueError, match="invalid symbolic mode clause"):
        _apply_symbolic_mode("u&x", 0o644)


# ---------------------------------------------------------------------------
# chmod — basic success paths
# ---------------------------------------------------------------------------


def test_chmod_octal_document(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["chmod", "0644", "myapp:/doc.xml"])
    assert result.exit_code == 0
    assert "updated" in result.output
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/doc.xml", 0o644)
    client_mock.get_permissions.assert_not_called()


def test_chmod_octal_without_leading_zero(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["chmod", "755", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/doc.xml", 0o755)


def test_chmod_octal_collection_root(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["chmod", "0755", "myapp:"])
    assert result.exit_code == 0
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/", 0o755)


def test_chmod_symbolic_add_execute(config_with_collection, client_mock, runner):
    """Symbolic mode: get_permissions is called first, then chmod_resource."""
    client_mock.get_permissions.return_value = 0o644
    result = runner.invoke(app, ["chmod", "u+x", "myapp:/doc.xml"])
    assert result.exit_code == 0
    assert "updated" in result.output
    client_mock.get_permissions.assert_called_once_with("/db/myapp/doc.xml")
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/doc.xml", 0o744)


def test_chmod_symbolic_remove_write(config_with_collection, client_mock, runner):
    client_mock.get_permissions.return_value = 0o777
    result = runner.invoke(app, ["chmod", "go-w", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/doc.xml", 0o755)


def test_chmod_symbolic_set_all(config_with_collection, client_mock, runner):
    client_mock.get_permissions.return_value = 0o755
    result = runner.invoke(app, ["chmod", "a=rw", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chmod_resource.assert_called_once_with("/db/myapp/doc.xml", 0o666)


# ---------------------------------------------------------------------------
# chmod -R (recursive)
# ---------------------------------------------------------------------------


def test_chmod_recursive_single_level(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = [
        ResourceEntry(name="a.xml"),
        ResourceEntry(name="b.xml"),
    ]
    result = runner.invoke(app, ["chmod", "-R", "0644", "myapp:/reports"])
    assert result.exit_code == 0
    assert "3 items" in result.output
    assert client_mock.chmod_resource.call_count == 3
    # All three calls use the same absolute mode, no get_permissions needed.
    client_mock.get_permissions.assert_not_called()


def test_chmod_recursive_nested(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    sub = CollectionEntry(name="sub")

    def list_side(path: str) -> list:
        if path.endswith("/reports"):
            return [sub, ResourceEntry(name="root.xml")]
        return [ResourceEntry(name="child.xml")]

    client_mock.list_collection.side_effect = list_side
    result = runner.invoke(app, ["chmod", "-R", "0644", "myapp:/reports"])
    assert result.exit_code == 0
    assert "4 items" in result.output


def test_chmod_recursive_symbolic_calls_get_permissions_per_item(
    config_with_collection, client_mock, runner
):
    """Symbolic recursive chmod queries each item's current permissions."""
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = [ResourceEntry(name="a.xml")]
    client_mock.get_permissions.return_value = 0o644

    result = runner.invoke(app, ["chmod", "-R", "u+x", "myapp:/reports"])
    assert result.exit_code == 0
    assert "2 items" in result.output
    # get_permissions called for root + 1 resource
    assert client_mock.get_permissions.call_count == 2
    # chmod_resource called with the computed mode (0o644 | u+x = 0o744)
    assert client_mock.chmod_resource.call_count == 2
    for c in client_mock.chmod_resource.call_args_list:
        assert c.args[1] == 0o744


def test_chmod_recursive_on_non_collection_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["chmod", "-R", "0644", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "not a collection" in result.output
    client_mock.chmod_resource.assert_not_called()


# ---------------------------------------------------------------------------
# chmod — validation / input errors
# ---------------------------------------------------------------------------


def test_chmod_invalid_mode_exits(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chmod", "0999", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "invalid mode" in result.output
    client_mock.chmod_resource.assert_not_called()


def test_chmod_garbage_mode_exits(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chmod", "hello!", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "invalid mode" in result.output


def test_chmod_unknown_collection_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chmod", "0644", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "collection 'ghost' not found" in result.output


# ---------------------------------------------------------------------------
# chmod — server / client errors
# ---------------------------------------------------------------------------


def test_chmod_query_error(config_with_collection, client_mock, runner):
    client_mock.chmod_resource.side_effect = ExistQueryError("Permission denied")
    result = runner.invoke(app, ["chmod", "0644", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "Permission denied" in result.output


def test_chmod_auth_error(config_with_collection, client_mock, runner):
    client_mock.chmod_resource.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["chmod", "0644", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_chmod_connection_error(config_with_collection, client_mock, runner):
    client_mock.chmod_resource.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["chmod", "0644", "myapp:/doc.xml"])
    assert result.exit_code == 1
