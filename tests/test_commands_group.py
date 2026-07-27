"""Tests for the group subcommands (ls, add, rm)."""

from unittest.mock import MagicMock

import pytest

from exist_shell.config import Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app
from exist_shell.models import GroupEntry


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the group command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.group.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_with_server(config_path, a_server):
    """Persist a config with one server but no collections."""
    Config.load().add_server(a_server)


@pytest.fixture
def config_with_two_servers(config_path, a_server):
    """Persist a config with two servers ("local" and "prod")."""
    from pydantic import SecretStr
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))


# ---------------------------------------------------------------------------
# group ls
# ---------------------------------------------------------------------------


def test_group_ls_lists_groups(config_with_server, client_mock, runner):
    """Group ls lists groups."""
    client_mock.list_groups.return_value = [
        GroupEntry(name="dba", members=["admin"]),
        GroupEntry(name="editors", members=["alice", "bob"]),
    ]
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 0
    assert "dba" in result.output
    assert "editors" in result.output
    assert "alice" in result.output


def test_group_ls_auto_selects_single_server(config_with_server, client_mock, runner):
    """Group ls auto selects single server."""
    client_mock.list_groups.return_value = []
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 0
    client_mock.list_groups.assert_called_once()


def test_group_ls_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """Group ls requires server when multiple."""
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_group_ls_explicit_server(config_with_server, client_mock, runner):
    """Group ls explicit server."""
    client_mock.list_groups.return_value = []
    result = runner.invoke(app, ["group", "ls", "--server", "local"])
    assert result.exit_code == 0


def test_group_ls_unknown_server_fails(config_with_server, client_mock, runner):
    """Group ls unknown server fails."""
    result = runner.invoke(app, ["group", "ls", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_group_ls_no_servers_fails(config_path, runner):
    """Group ls no servers fails."""
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_group_ls_auth_error(config_with_server, client_mock, runner):
    """Group ls auth error."""
    client_mock.list_groups.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_group_ls_connection_error(config_with_server, client_mock, runner):
    """Group ls connection error."""
    client_mock.list_groups.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["group", "ls"])
    assert result.exit_code == 1


def test_group_ls_at_server_selects_server(config_with_server, client_mock, runner):
    """Group ls at server selects server."""
    client_mock.list_groups.return_value = []
    result = runner.invoke(app, ["group", "ls", "@local"])
    assert result.exit_code == 0
    client_mock.list_groups.assert_called_once()


def test_group_ls_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """Group ls at server conflict with flag fails."""
    result = runner.invoke(app, ["group", "ls", "@local", "--server", "local"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_group_ls_at_server_missing_nick_fails(config_with_server, client_mock, runner):
    """Group ls at server missing nick fails."""
    result = runner.invoke(app, ["group", "ls", "@"])
    assert result.exit_code == 1
    assert "empty" in result.output


def test_group_ls_at_server_no_at_prefix_fails(config_with_server, client_mock, runner):
    """Group ls at server no at prefix fails."""
    result = runner.invoke(app, ["group", "ls", "notvalid"])
    assert result.exit_code == 1
    assert "@nick" in result.output


# ---------------------------------------------------------------------------
# group add
# ---------------------------------------------------------------------------


def test_group_add_success(config_with_server, client_mock, runner):
    """Group add success."""
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 0
    assert "editors" in result.output
    client_mock.create_group.assert_called_once_with("editors")


def test_group_add_at_server_selects_server(config_with_server, client_mock, runner):
    """Group add at server selects server."""
    result = runner.invoke(app, ["group", "add", "editors@local"])
    assert result.exit_code == 0
    client_mock.create_group.assert_called_once_with("editors")


def test_group_add_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """Group add at server conflict with flag fails."""
    result = runner.invoke(app, ["group", "add", "editors@local", "--server", "local"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_group_add_empty_groupname_at_server_fails(config_with_server, client_mock, runner):
    """Group add empty groupname at server fails."""
    result = runner.invoke(app, ["group", "add", "@local"])
    assert result.exit_code == 1
    assert "group name cannot be empty" in result.output


def test_group_add_at_server_unknown_fails(config_with_server, client_mock, runner):
    """Group add at server unknown fails."""
    result = runner.invoke(app, ["group", "add", "editors@ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_group_add_no_servers_fails(config_path, runner):
    """Group add no servers fails."""
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_group_add_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """Group add requires server when multiple."""
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_group_add_auth_error(config_with_server, client_mock, runner):
    """Group add auth error."""
    client_mock.create_group.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_group_add_connection_error(config_with_server, client_mock, runner):
    """Group add connection error."""
    client_mock.create_group.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 1


def test_group_add_query_error(config_with_server, client_mock, runner):
    """Group add query error."""
    client_mock.create_group.side_effect = ExistQueryError("group already exists")
    result = runner.invoke(app, ["group", "add", "editors"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# group rm
# ---------------------------------------------------------------------------


def test_group_rm_with_yes_flag(config_with_server, client_mock, runner):
    """Group rm with yes flag."""
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 0
    assert "editors" in result.output
    client_mock.delete_group.assert_called_once_with("editors")


def test_group_rm_confirms_interactively(config_with_server, client_mock, runner):
    """Group rm confirms interactively."""
    result = runner.invoke(app, ["group", "rm", "editors"], input="y\n")
    assert result.exit_code == 0
    client_mock.delete_group.assert_called_once_with("editors")


def test_group_rm_abort_on_no(config_with_server, client_mock, runner):
    """Group rm abort on no."""
    result = runner.invoke(app, ["group", "rm", "editors"], input="n\n")
    assert result.exit_code != 0
    client_mock.delete_group.assert_not_called()


def test_group_rm_at_server_selects_server(config_with_server, client_mock, runner):
    """Group rm at server selects server."""
    result = runner.invoke(app, ["group", "rm", "editors@local", "--yes"])
    assert result.exit_code == 0
    client_mock.delete_group.assert_called_once_with("editors")


def test_group_rm_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """Group rm at server conflict with flag fails."""
    result = runner.invoke(app, ["group", "rm", "editors@local", "--server", "local", "--yes"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_group_rm_empty_groupname_at_server_fails(config_with_server, client_mock, runner):
    """Group rm empty groupname at server fails."""
    result = runner.invoke(app, ["group", "rm", "@local", "--yes"])
    assert result.exit_code == 1
    assert "group name cannot be empty" in result.output


def test_group_rm_at_server_unknown_fails(config_with_server, client_mock, runner):
    """Group rm at server unknown fails."""
    result = runner.invoke(app, ["group", "rm", "editors@ghost", "--yes"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_group_rm_no_servers_fails(config_path, runner):
    """Group rm no servers fails."""
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_group_rm_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """Group rm requires server when multiple."""
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_group_rm_auth_error(config_with_server, client_mock, runner):
    """Group rm auth error."""
    client_mock.delete_group.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_group_rm_connection_error(config_with_server, client_mock, runner):
    """Group rm connection error."""
    client_mock.delete_group.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 1


def test_group_rm_query_error(config_with_server, client_mock, runner):
    """Group rm query error."""
    client_mock.delete_group.side_effect = ExistQueryError("group not found")
    result = runner.invoke(app, ["group", "rm", "editors", "--yes"])
    assert result.exit_code == 1
