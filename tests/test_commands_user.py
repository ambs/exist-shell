"""Tests for the user subcommands (ls, add, rm, info)."""

from unittest.mock import MagicMock

import pytest

from exist_shell.config import Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app
from exist_shell.models import UserEntry, UserInfo


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.user.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_with_server(config_path, a_server):
    Config.load().add_server(a_server)


@pytest.fixture
def config_with_two_servers(config_path, a_server):
    from pydantic import SecretStr
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))


# ---------------------------------------------------------------------------
# user ls
# ---------------------------------------------------------------------------


def test_user_ls_lists_users(config_with_server, client_mock, runner):
    client_mock.list_users.return_value = [
        UserEntry(username="admin", groups=["dba"]),
        UserEntry(username="alice", groups=["editors", "users"]),
    ]
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 0
    assert "admin" in result.output
    assert "dba" in result.output
    assert "alice" in result.output
    assert "editors" in result.output


def test_user_ls_auto_selects_single_server(config_with_server, client_mock, runner):
    client_mock.list_users.return_value = []
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 0
    client_mock.list_users.assert_called_once()


def test_user_ls_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_ls_explicit_server(config_with_server, client_mock, runner):
    client_mock.list_users.return_value = []
    result = runner.invoke(app, ["user", "ls", "--server", "local"])
    assert result.exit_code == 0


def test_user_ls_unknown_server_fails(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "ls", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_ls_no_servers_fails(config_path, runner):
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_ls_auth_error(config_with_server, client_mock, runner):
    client_mock.list_users.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_ls_connection_error(config_with_server, client_mock, runner):
    client_mock.list_users.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user add
# ---------------------------------------------------------------------------


def test_user_add_success(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors", "--password", "test-pw"])
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors"])


def test_user_add_multiple_groups(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors,users", "--password", "test-pw"])
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors", "users"])


def test_user_add_default_group_is_guest(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw"])
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["guest"])


def test_user_add_prompts_for_password(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors"], input="test-pw\ntest-pw\n")
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors"])


def test_user_add_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_add_auth_error(config_with_server, client_mock, runner):
    client_mock.create_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_add_connection_error(config_with_server, client_mock, runner):
    client_mock.create_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1


def test_user_add_query_error(config_with_server, client_mock, runner):
    client_mock.create_user.side_effect = ExistQueryError("account already exists")
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user rm
# ---------------------------------------------------------------------------


def test_user_rm_with_yes_flag(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.delete_user.assert_called_once_with("alice")


def test_user_rm_confirms_interactively(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "rm", "alice"], input="y\n")
    assert result.exit_code == 0
    client_mock.delete_user.assert_called_once_with("alice")


def test_user_rm_abort_on_no(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["user", "rm", "alice"], input="n\n")
    assert result.exit_code != 0
    client_mock.delete_user.assert_not_called()


def test_user_rm_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_rm_auth_error(config_with_server, client_mock, runner):
    client_mock.delete_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_rm_connection_error(config_with_server, client_mock, runner):
    client_mock.delete_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1


def test_user_rm_query_error(config_with_server, client_mock, runner):
    client_mock.delete_user.side_effect = ExistQueryError("account not found")
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user info
# ---------------------------------------------------------------------------


def test_user_info_shows_details(config_with_server, client_mock, runner):
    client_mock.get_user.return_value = UserInfo(
        username="alice",
        full_name="Alice Smith",
        groups=["editors", "users"],
        enabled=True,
    )
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 0
    assert "alice" in result.output
    assert "Alice Smith" in result.output
    assert "editors" in result.output
    assert "True" in result.output


def test_user_info_omits_full_name_when_absent(config_with_server, client_mock, runner):
    client_mock.get_user.return_value = UserInfo(
        username="alice",
        full_name=None,
        groups=["guest"],
        enabled=True,
    )
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 0
    assert "Full name" not in result.output


def test_user_info_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_info_auth_error(config_with_server, client_mock, runner):
    client_mock.get_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_info_connection_error(config_with_server, client_mock, runner):
    client_mock.get_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1


def test_user_info_query_error(config_with_server, client_mock, runner):
    client_mock.get_user.side_effect = ExistQueryError("account not found")
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
