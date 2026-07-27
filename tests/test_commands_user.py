"""Tests for the user subcommands (ls, add, rm, info)."""

from unittest.mock import MagicMock, patch

import pytest

import exist_shell.commands.user as user_mod
from exist_shell.config import Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app
from exist_shell.models import UserEntry, UserInfo


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the user command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.user.ExistClient", lambda _: mock)
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
# user ls
# ---------------------------------------------------------------------------


def test_user_ls_lists_users(config_with_server, client_mock, runner):
    """User ls lists users."""
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
    """User ls auto selects single server."""
    client_mock.list_users.return_value = []
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 0
    client_mock.list_users.assert_called_once()


def test_user_ls_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """User ls requires server when multiple."""
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_ls_explicit_server(config_with_server, client_mock, runner):
    """User ls explicit server."""
    client_mock.list_users.return_value = []
    result = runner.invoke(app, ["user", "ls", "--server", "local"])
    assert result.exit_code == 0


def test_user_ls_unknown_server_fails(config_with_server, client_mock, runner):
    """User ls unknown server fails."""
    result = runner.invoke(app, ["user", "ls", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_ls_no_servers_fails(config_path, runner):
    """User ls no servers fails."""
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_ls_auth_error(config_with_server, client_mock, runner):
    """User ls auth error."""
    client_mock.list_users.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_ls_connection_error(config_with_server, client_mock, runner):
    """User ls connection error."""
    client_mock.list_users.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "ls"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user add
# ---------------------------------------------------------------------------


def test_user_add_success(config_with_server, client_mock, runner):
    """User add success."""
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors", "--password", "test-pw"])
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors"])


def test_user_add_multiple_groups(config_with_server, client_mock, runner):
    """User add multiple groups."""
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors,users", "--password", "test-pw"])
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors", "users"])


def test_user_add_default_group_is_guest(config_with_server, client_mock, runner):
    """User add default group is guest."""
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw"])
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["guest"])


def test_user_add_prompts_for_password(config_with_server, client_mock, runner):
    """User add prompts for password."""
    result = runner.invoke(app, ["user", "add", "alice", "--group", "editors"], input="test-pw\ntest-pw\n")
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "test-pw", ["editors"])


def test_user_add_no_servers_fails(config_path, runner):
    """User add no servers fails."""
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_add_unknown_server_fails(config_with_server, client_mock, runner):
    """User add unknown server fails."""
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_add_empty_group_fails(config_with_server, client_mock, runner):
    """User add empty group fails."""
    result = runner.invoke(app, ["user", "add", "alice", "--group", "  ,  ", "--password", "test-pw"])
    assert result.exit_code == 1
    assert "group" in result.output


def test_user_add_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """User add requires server when multiple."""
    result = runner.invoke(app, ["user", "add", "alice", "--password", "test-pw"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_add_auth_error(config_with_server, client_mock, runner):
    """User add auth error."""
    client_mock.create_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_add_connection_error(config_with_server, client_mock, runner):
    """User add connection error."""
    client_mock.create_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1


def test_user_add_query_error(config_with_server, client_mock, runner):
    """User add query error."""
    client_mock.create_user.side_effect = ExistQueryError("account already exists")
    result = runner.invoke(app, ["user", "add", "alice", "--password", "x"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user rm
# ---------------------------------------------------------------------------


def test_user_rm_with_yes_flag(config_with_server, client_mock, runner):
    """User rm with yes flag."""
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.delete_user.assert_called_once_with("alice")


def test_user_rm_confirms_interactively(config_with_server, client_mock, runner):
    """User rm confirms interactively."""
    result = runner.invoke(app, ["user", "rm", "alice"], input="y\n")
    assert result.exit_code == 0
    client_mock.delete_user.assert_called_once_with("alice")


def test_user_rm_abort_on_no(config_with_server, client_mock, runner):
    """User rm abort on no."""
    result = runner.invoke(app, ["user", "rm", "alice"], input="n\n")
    assert result.exit_code != 0
    client_mock.delete_user.assert_not_called()


def test_user_rm_no_servers_fails(config_path, runner):
    """User rm no servers fails."""
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_rm_unknown_server_fails(config_with_server, client_mock, runner):
    """User rm unknown server fails."""
    result = runner.invoke(app, ["user", "rm", "alice", "--yes", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_rm_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """User rm requires server when multiple."""
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_rm_auth_error(config_with_server, client_mock, runner):
    """User rm auth error."""
    client_mock.delete_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_rm_connection_error(config_with_server, client_mock, runner):
    """User rm connection error."""
    client_mock.delete_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1


def test_user_rm_query_error(config_with_server, client_mock, runner):
    """User rm query error."""
    client_mock.delete_user.side_effect = ExistQueryError("account not found")
    result = runner.invoke(app, ["user", "rm", "alice", "--yes"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# user info
# ---------------------------------------------------------------------------


def test_user_info_shows_details(config_with_server, client_mock, runner):
    """User info shows details."""
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
    """User info omits full name when absent."""
    client_mock.get_user.return_value = UserInfo(
        username="alice",
        full_name=None,
        groups=["guest"],
        enabled=True,
    )
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 0
    assert "Full name" not in result.output


def test_user_info_no_servers_fails(config_path, runner):
    """User info no servers fails."""
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_info_unknown_server_fails(config_with_server, client_mock, runner):
    """User info unknown server fails."""
    result = runner.invoke(app, ["user", "info", "alice", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_info_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """User info requires server when multiple."""
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_info_auth_error(config_with_server, client_mock, runner):
    """User info auth error."""
    client_mock.get_user.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_info_connection_error(config_with_server, client_mock, runner):
    """User info connection error."""
    client_mock.get_user.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1


def test_user_info_query_error(config_with_server, client_mock, runner):
    """User info query error."""
    client_mock.get_user.side_effect = ExistQueryError("account not found")
    result = runner.invoke(app, ["user", "info", "alice"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# @server syntax — user ls
# ---------------------------------------------------------------------------


def test_user_ls_at_server_selects_server(config_with_server, client_mock, runner):
    """User ls at server selects server."""
    client_mock.list_users.return_value = []
    result = runner.invoke(app, ["user", "ls", "@local"])
    assert result.exit_code == 0
    client_mock.list_users.assert_called_once()


def test_user_ls_at_server_unknown_fails(config_with_server, client_mock, runner):
    """User ls at server unknown fails."""
    result = runner.invoke(app, ["user", "ls", "@ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_ls_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """User ls at server conflict with flag fails."""
    result = runner.invoke(app, ["user", "ls", "@local", "--server", "local"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_user_ls_at_server_missing_nick_fails(config_with_server, client_mock, runner):
    """User ls at server missing nick fails."""
    result = runner.invoke(app, ["user", "ls", "@"])
    assert result.exit_code == 1
    assert "empty" in result.output


def test_user_ls_at_server_no_at_prefix_fails(config_with_server, client_mock, runner):
    """User ls at server no at prefix fails."""
    result = runner.invoke(app, ["user", "ls", "notvalid"])
    assert result.exit_code == 1
    assert "@nick" in result.output


# ---------------------------------------------------------------------------
# @server syntax — user add
# ---------------------------------------------------------------------------


def test_user_add_at_server_selects_server(config_with_server, client_mock, runner):
    """User add at server selects server."""
    result = runner.invoke(app, ["user", "add", "alice@local", "--password", "pw"])
    assert result.exit_code == 0
    client_mock.create_user.assert_called_once_with("alice", "pw", ["guest"])


def test_user_add_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """User add at server conflict with flag fails."""
    result = runner.invoke(app, ["user", "add", "alice@local", "--server", "local", "--password", "pw"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_user_add_empty_username_at_server_fails(config_with_server, client_mock, runner):
    """User add empty username at server fails."""
    result = runner.invoke(app, ["user", "add", "@local", "--password", "pw"])
    assert result.exit_code == 1
    assert "username cannot be empty" in result.output


def test_user_add_at_server_unknown_fails(config_with_server, client_mock, runner):
    """User add at server unknown fails."""
    result = runner.invoke(app, ["user", "add", "alice@ghost", "--password", "pw"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# @server syntax — user rm
# ---------------------------------------------------------------------------


def test_user_rm_at_server_selects_server(config_with_server, client_mock, runner):
    """User rm at server selects server."""
    result = runner.invoke(app, ["user", "rm", "alice@local", "--yes"])
    assert result.exit_code == 0
    client_mock.delete_user.assert_called_once_with("alice")


def test_user_rm_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """User rm at server conflict with flag fails."""
    result = runner.invoke(app, ["user", "rm", "alice@local", "--server", "local", "--yes"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_user_rm_empty_username_at_server_fails(config_with_server, client_mock, runner):
    """User rm empty username at server fails."""
    result = runner.invoke(app, ["user", "rm", "@local", "--yes"])
    assert result.exit_code == 1
    assert "username cannot be empty" in result.output


def test_user_rm_at_server_unknown_fails(config_with_server, client_mock, runner):
    """User rm at server unknown fails."""
    result = runner.invoke(app, ["user", "rm", "alice@ghost", "--yes"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# @server syntax — user info
# ---------------------------------------------------------------------------


def test_user_info_at_server_selects_server(config_with_server, client_mock, runner):
    """User info at server selects server."""
    from exist_shell.models import UserInfo
    client_mock.get_user.return_value = UserInfo(
        username="alice", full_name=None, groups=["guest"], enabled=True
    )
    result = runner.invoke(app, ["user", "info", "alice@local"])
    assert result.exit_code == 0
    client_mock.get_user.assert_called_once_with("alice")


def test_user_info_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """User info at server conflict with flag fails."""
    result = runner.invoke(app, ["user", "info", "alice@local", "--server", "local"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_user_info_empty_username_at_server_fails(config_with_server, client_mock, runner):
    """User info empty username at server fails."""
    result = runner.invoke(app, ["user", "info", "@local"])
    assert result.exit_code == 1
    assert "username cannot be empty" in result.output


def test_user_info_at_server_unknown_fails(config_with_server, client_mock, runner):
    """User info at server unknown fails."""
    result = runner.invoke(app, ["user", "info", "alice@ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# user passwd
# ---------------------------------------------------------------------------


def test_user_passwd_non_tty_stdin_reads_password(config_with_server, client_mock, runner):
    """User passwd non tty stdin reads password."""
    # CliRunner provides a non-TTY stdin, so the auto-detection path is exercised.
    result = runner.invoke(app, ["user", "passwd", "alice"], input="newpw\n")
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.change_password.assert_called_once_with("alice", "newpw")


def test_user_passwd_tty_stdin_prompts_with_confirmation(config_with_server, client_mock, runner):
    """User passwd tty stdin prompts with confirmation."""
    # CliRunner always replaces sys.stdin inside isolation(), so patching sys.stdin
    # directly is unreliable.  Instead we patch _stdin_is_tty (the extracted helper)
    # to return True, and mock typer.prompt so no real TTY input is needed.
    with patch.object(user_mod, "_stdin_is_tty", return_value=True), \
         patch.object(user_mod.typer, "prompt", return_value="newpw") as mock_prompt:
        result = runner.invoke(app, ["user", "passwd", "alice"])
    assert result.exit_code == 0
    mock_prompt.assert_called_once_with(
        "New password for 'alice'", hide_input=True, confirmation_prompt=True
    )
    client_mock.change_password.assert_called_once_with("alice", "newpw")


def test_user_passwd_reads_from_stdin(config_with_server, client_mock, runner):
    """User passwd reads from stdin."""
    result = runner.invoke(app, ["user", "passwd", "alice", "--stdin"], input="newpw\n")
    assert result.exit_code == 0
    assert "alice" in result.output
    client_mock.change_password.assert_called_once_with("alice", "newpw")


def test_user_passwd_no_servers_fails(config_path, runner):
    """User passwd no servers fails."""
    result = runner.invoke(app, ["user", "passwd", "alice"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_user_passwd_unknown_server_fails(config_with_server, client_mock, runner):
    """User passwd unknown server fails."""
    result = runner.invoke(app, ["user", "passwd", "alice", "--server", "ghost"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "not found" in result.output


def test_user_passwd_requires_server_when_multiple(config_with_two_servers, client_mock, runner):
    """User passwd requires server when multiple."""
    result = runner.invoke(app, ["user", "passwd", "alice"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "--server" in result.output


def test_user_passwd_auth_error(config_with_server, client_mock, runner):
    """User passwd auth error."""
    client_mock.change_password.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["user", "passwd", "alice"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_user_passwd_connection_error(config_with_server, client_mock, runner):
    """User passwd connection error."""
    client_mock.change_password.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["user", "passwd", "alice"], input="pw\npw\n")
    assert result.exit_code == 1


def test_user_passwd_query_error(config_with_server, client_mock, runner):
    """User passwd query error."""
    client_mock.change_password.side_effect = ExistQueryError("user not found")
    result = runner.invoke(app, ["user", "passwd", "alice"], input="pw\npw\n")
    assert result.exit_code == 1


def test_user_passwd_at_server_selects_server(config_with_server, client_mock, runner):
    """User passwd at server selects server."""
    result = runner.invoke(app, ["user", "passwd", "alice@local"], input="pw\npw\n")
    assert result.exit_code == 0
    client_mock.change_password.assert_called_once_with("alice", "pw")


def test_user_passwd_at_server_conflict_with_flag_fails(config_with_server, client_mock, runner):
    """User passwd at server conflict with flag fails."""
    result = runner.invoke(app, ["user", "passwd", "alice@local", "--server", "local"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_user_passwd_empty_username_fails(config_with_server, client_mock, runner):
    """User passwd empty username fails."""
    result = runner.invoke(app, ["user", "passwd", "@local"], input="pw\npw\n")
    assert result.exit_code == 1
    assert "username cannot be empty" in result.output
