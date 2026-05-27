"""Tests for the chown command."""

from unittest.mock import MagicMock, call

import pytest

from exist_shell.commands.chown import _parse_spec
from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app
from exist_shell.models import CollectionEntry, ResourceEntry
from pydantic import SecretStr


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.chown.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_with_collection(config_path, a_server):
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))


# ---------------------------------------------------------------------------
# _parse_spec
# ---------------------------------------------------------------------------


def test_parse_spec_owner_only():
    assert _parse_spec("alice") == ("alice", None)


def test_parse_spec_group_only():
    assert _parse_spec(":editors") == (None, "editors")


def test_parse_spec_both():
    assert _parse_spec("alice:editors") == ("alice", "editors")


def test_parse_spec_strips_server_prefix():
    assert _parse_spec("prod@alice:editors") == ("alice", "editors")


def test_parse_spec_server_prefix_owner_only():
    assert _parse_spec("prod@alice") == ("alice", None)


def test_parse_spec_server_prefix_group_only():
    assert _parse_spec("prod@:editors") == (None, "editors")


def test_parse_spec_empty_returns_none_pair():
    assert _parse_spec("") == (None, None)


def test_parse_spec_colon_only_returns_none_pair():
    assert _parse_spec(":") == (None, None)


# ---------------------------------------------------------------------------
# chown — basic success paths
# ---------------------------------------------------------------------------


def test_chown_owner_only(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "alice", "myapp:/doc.xml"])
    assert result.exit_code == 0
    assert "updated" in result.output
    client_mock.chown_resource.assert_called_once_with("/db/myapp/doc.xml", "alice", None)


def test_chown_group_only(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", ":editors", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chown_resource.assert_called_once_with("/db/myapp/doc.xml", None, "editors")


def test_chown_owner_and_group(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "alice:editors", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chown_resource.assert_called_once_with("/db/myapp/doc.xml", "alice", "editors")


def test_chown_server_prefix_stripped(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "local@alice:editors", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.chown_resource.assert_called_once_with("/db/myapp/doc.xml", "alice", "editors")


def test_chown_collection_root_path(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "alice", "myapp:"])
    assert result.exit_code == 0
    client_mock.chown_resource.assert_called_once_with("/db/myapp/", "alice", None)


# ---------------------------------------------------------------------------
# chown -R (recursive)
# ---------------------------------------------------------------------------


def test_chown_recursive_single_level(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = [
        ResourceEntry(name="a.xml"),
        ResourceEntry(name="b.xml"),
    ]
    result = runner.invoke(app, ["chown", "-R", "alice", "myapp:/reports"])
    assert result.exit_code == 0
    assert "3 items" in result.output
    assert client_mock.chown_resource.call_count == 3


def test_chown_recursive_nested(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    sub_entry = CollectionEntry(name="sub")

    def list_collection_side(path):
        if path.endswith("/reports"):
            return [sub_entry, ResourceEntry(name="root.xml")]
        return [ResourceEntry(name="child.xml")]

    client_mock.list_collection.side_effect = list_collection_side
    result = runner.invoke(app, ["chown", "-R", "alice", "myapp:/reports"])
    assert result.exit_code == 0
    assert "4 items" in result.output


def test_chown_recursive_on_non_collection_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["chown", "-R", "alice", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "not a collection" in result.output
    client_mock.chown_resource.assert_not_called()


# ---------------------------------------------------------------------------
# chown — validation / input errors
# ---------------------------------------------------------------------------


def test_chown_empty_spec_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "specify at least" in result.output


def test_chown_colon_only_spec_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", ":", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "specify at least" in result.output


def test_chown_unknown_collection_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "alice", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "collection 'ghost' not found" in result.output


def test_chown_server_prefix_mismatch_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["chown", "other@alice", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "other" in result.output
    assert "local" in result.output
    client_mock.chown_resource.assert_not_called()


# ---------------------------------------------------------------------------
# chown — server / client errors
# ---------------------------------------------------------------------------


def test_chown_query_error_user_not_found(config_with_collection, client_mock, runner):
    client_mock.chown_resource.side_effect = ExistQueryError("User not found: nobody")
    result = runner.invoke(app, ["chown", "nobody", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "User not found" in result.output


def test_chown_query_error_group_not_found(config_with_collection, client_mock, runner):
    client_mock.chown_resource.side_effect = ExistQueryError("Group not found: ghost")
    result = runner.invoke(app, ["chown", ":ghost", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "Group not found" in result.output


def test_chown_query_error_permission_denied(config_with_collection, client_mock, runner):
    client_mock.chown_resource.side_effect = ExistQueryError("Permission denied")
    result = runner.invoke(app, ["chown", "alice", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "Permission denied" in result.output


def test_chown_auth_error(config_with_collection, client_mock, runner):
    client_mock.chown_resource.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["chown", "alice", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_chown_connection_error(config_with_collection, client_mock, runner):
    client_mock.chown_resource.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["chown", "alice", "myapp:/doc.xml"])
    assert result.exit_code == 1
