"""Tests for the server subcommands (add, rename, rm) and default listing."""

from unittest.mock import MagicMock

import pytest

from pydantic import SecretStr

from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the server command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.server.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_server_ls_empty(config_path, runner):
    """Server ls empty."""
    result = runner.invoke(app, ["server", "ls"])
    assert result.exit_code == 0
    assert result.output == ""


def test_server_ls_lists_servers(config_path, a_server, runner):
    """Server ls lists servers."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "ls"])
    assert result.exit_code == 0
    assert "local" in result.output
    assert "localhost:8080" in result.output


def test_server_add_success(config_path, client_mock, runner):
    """Server add success."""
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 0
    assert "localhost" in Config.load().servers


def test_server_add_uses_custom_nick(config_path, client_mock, runner):
    """Server add uses custom nick."""
    result = runner.invoke(app, ["server", "add", "myserver.example.com", "--nick", "prod"], input="\n")
    assert result.exit_code == 0
    assert "prod" in Config.load().servers


def test_server_add_duplicate_nick_fails(config_path, a_server, client_mock, runner):
    """Server add duplicate nick fails."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "add", "localhost", "--nick", "local"], input="\n")
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_server_add_connection_error_fails(config_path, client_mock, runner):
    """Server add connection error fails."""
    client_mock.check_connection.side_effect = ExistConnectionError("http://localhost:8080/exist/rest/db", Exception("refused"))
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 1
    assert "localhost" not in Config.load().servers


def test_server_add_auth_error_fails(config_path, client_mock, runner):
    """Server add auth error fails."""
    client_mock.check_connection.side_effect = ExistAuthError("http://localhost:8080/exist/rest/db")
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 1
    assert "localhost" not in Config.load().servers


# ---------------------------------------------------------------------------
# server rm
# ---------------------------------------------------------------------------


def test_server_rm_removes_server(config_path, a_server, runner):
    """Server rm removes server."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rm", "local"])
    assert result.exit_code == 0
    assert "local" not in Config.load().servers
    assert "removed" in result.output


def test_server_rm_unknown_nick_fails(config_path, runner):
    """Server rm unknown nick fails."""
    result = runner.invoke(app, ["server", "rm", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_server_rm_cascades_collections(config_path, a_server, runner):
    """Server rm cascades collections."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="other", server_nick="local", name="other"))
    result = runner.invoke(app, ["server", "rm", "local"])
    assert result.exit_code == 0
    config = Config.load()
    assert "myapp" not in config.collections
    assert "other" not in config.collections


def test_server_rm_cascade_message_singular(config_path, a_server, runner):
    """Server rm cascade message singular."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed 1 collection: myapp" in result.output


def test_server_rm_cascade_message_plural(config_path, a_server, runner):
    """Server rm cascade message plural."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="other", server_nick="local", name="other"))
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed 2 collections:" in result.output


def test_server_rm_no_cascade_message_when_no_collections(config_path, a_server, runner):
    """Server rm no cascade message when no collections."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed" not in result.output


def test_server_rm_keeps_other_server_collections(config_path, a_server, runner):
    """Server rm keeps other server collections."""
    from pydantic import SecretStr
    from exist_shell.config import Server
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="prodapp", server_nick="prod", name="prodapp"))
    runner.invoke(app, ["server", "rm", "local"])
    assert "prodapp" in Config.load().collections


def test_server_rm_makes_no_http_call(config_path, a_server, client_mock, runner):
    """Server rm makes no http call."""
    Config.load().add_server(a_server)
    runner.invoke(app, ["server", "rm", "local"])
    client_mock.check_connection.assert_not_called()


# ---------------------------------------------------------------------------
# server rename
# ---------------------------------------------------------------------------


def test_server_rename_renames_server(config_path, a_server, runner):
    """Server rename renames server."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert result.exit_code == 0
    config = Config.load()
    assert "prod" in config.servers
    assert "local" not in config.servers


def test_server_rename_updates_nick_field(config_path, a_server, runner):
    """Server rename updates nick field."""
    Config.load().add_server(a_server)
    runner.invoke(app, ["server", "rename", "local", "prod"])
    assert Config.load().servers["prod"].nick == "prod"


def test_server_rename_updates_collection_references(config_path, a_server, runner):
    """Server rename updates collection references."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert result.exit_code == 0
    assert Config.load().collections["myapp"].server_nick == "prod"


def test_server_rename_reports_updated_collections_singular(config_path, a_server, runner):
    """Server rename reports updated collections singular."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert "Also updated 1 collection: myapp" in result.output


def test_server_rename_reports_updated_collections_plural(config_path, a_server, runner):
    """Server rename reports updated collections plural."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="other", server_nick="local", name="other"))
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert "Also updated 2 collections:" in result.output


def test_server_rename_no_cascade_message_when_no_collections(config_path, a_server, runner):
    """Server rename no cascade message when no collections."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert "Also updated" not in result.output


def test_server_rename_prints_success_message(config_path, a_server, runner):
    """Server rename prints success message."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert "Server 'local' renamed to 'prod'." in result.output


def test_server_rename_unknown_old_nick_fails(config_path, runner):
    """Server rename unknown old nick fails."""
    result = runner.invoke(app, ["server", "rename", "ghost", "prod"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_server_rename_duplicate_new_nick_fails(config_path, a_server, runner):
    """Server rename duplicate new nick fails."""
    from pydantic import SecretStr
    from exist_shell.config import Server
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    result = runner.invoke(app, ["server", "rename", "local", "prod"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_server_rename_same_nick_fails(config_path, a_server, runner):
    """Server rename same nick fails."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rename", "local", "local"])
    assert result.exit_code == 1
    assert "same as the old nick" in result.output


def test_server_rename_invalid_new_nick_fails(config_path, a_server, runner):
    """Server rename invalid new nick fails."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rename", "local", "invalid!nick"])
    assert result.exit_code == 1
    assert "not a valid" in result.output


def test_server_rename_makes_no_http_call(config_path, a_server, client_mock, runner):
    """Server rename makes no http call."""
    Config.load().add_server(a_server)
    runner.invoke(app, ["server", "rename", "local", "prod"])
    client_mock.check_connection.assert_not_called()


def test_server_rename_keeps_other_server_collections(config_path, a_server, runner):
    """Server rename keeps other server collections."""
    from pydantic import SecretStr
    from exist_shell.config import Server
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="prodapp", server_nick="prod", name="prodapp"))
    runner.invoke(app, ["server", "rename", "local", "staging"])
    assert Config.load().collections["prodapp"].server_nick == "prod"


# ---------------------------------------------------------------------------
# _complete_server_nick
# ---------------------------------------------------------------------------


def test_complete_server_nick_returns_matching_nicks(config_path, a_server):
    """Complete server nick returns matching nicks."""
    from exist_shell.commands.server import _complete_server_nick
    Config.load().add_server(a_server)
    assert _complete_server_nick("lo") == ["local"]


def test_complete_server_nick_returns_all_when_empty_prefix(config_path, a_server):
    """Complete server nick returns all when empty prefix."""
    from exist_shell.commands.server import _complete_server_nick
    Config.load().add_server(a_server)
    assert _complete_server_nick("") == ["local"]


def test_complete_server_nick_returns_empty_when_no_match(config_path, a_server):
    """Complete server nick returns empty when no match."""
    from exist_shell.commands.server import _complete_server_nick
    Config.load().add_server(a_server)
    assert _complete_server_nick("xyz") == []


def test_complete_server_nick_returns_empty_on_config_error(monkeypatch):
    """Complete server nick returns empty on config error."""
    from exist_shell.commands.server import _complete_server_nick
    monkeypatch.setattr("exist_shell.commands.server.Config.load", lambda: (_ for _ in ()).throw(Exception("fail")))
    assert _complete_server_nick("") == []


# ---------------------------------------------------------------------------
# server status / ping
# ---------------------------------------------------------------------------


def test_server_status_single_ok(config_path, a_server, client_mock, runner):
    """Server status prints URL, version, and OK with latency for one server."""
    Config.load().add_server(a_server)
    client_mock.server_version.return_value = "6.2.0"
    result = runner.invoke(app, ["server", "status", "local"])
    assert result.exit_code == 0
    assert "Server:   http://localhost:8080/exist" in result.output
    assert "Version:  6.2.0" in result.output
    assert "Status:   OK (" in result.output
    assert "ms)" in result.output


def test_server_status_connection_failure_exits_1(config_path, a_server, client_mock, runner):
    """Server status exits 1 and reports FAIL on connection failure."""
    Config.load().add_server(a_server)
    client_mock.server_version.side_effect = ExistConnectionError(
        "http://localhost:8080/exist/rest/db", Exception("refused")
    )
    result = runner.invoke(app, ["server", "status", "local"])
    assert result.exit_code == 1
    assert "FAIL (cannot connect: refused)" in result.output
    assert "Version:  -" in result.output


def test_server_status_auth_failure_exits_1(config_path, a_server, client_mock, runner):
    """Server status exits 1 and reports FAIL on authentication failure."""
    Config.load().add_server(a_server)
    client_mock.server_version.side_effect = ExistAuthError("http://localhost:8080/exist/rest/db")
    result = runner.invoke(app, ["server", "status", "local"])
    assert result.exit_code == 1
    assert "FAIL (authentication failed)" in result.output


def test_server_status_unknown_nick_fails(config_path, a_server, runner):
    """Server status exits 1 on an unknown server nick."""
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "status", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_server_status_no_servers_fails(config_path, runner):
    """Server status exits 1 when no servers are configured."""
    result = runner.invoke(app, ["server", "status"])
    assert result.exit_code == 1
    assert "no servers configured" in result.output


def test_server_status_all_servers_mixed_exits_1(config_path, a_server, client_mock, runner):
    """Server status without a nick reports every server and exits 1 on any failure."""
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", port=8080, user="admin", password=SecretStr("")))
    client_mock.server_version.side_effect = [
        "6.2.0",
        ExistConnectionError("http://prod.example.com:8080/exist/rest/db", Exception("refused")),
    ]
    result = runner.invoke(app, ["server", "status"])
    assert result.exit_code == 1
    assert "local" in result.output
    assert "6.2.0" in result.output
    assert "OK (" in result.output
    assert "prod" in result.output
    assert "FAIL (cannot connect: refused)" in result.output


def test_server_status_all_servers_ok_exits_0(config_path, a_server, client_mock, runner):
    """Server status without a nick exits 0 when every server is reachable."""
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", port=8080, user="admin", password=SecretStr("")))
    client_mock.server_version.side_effect = ["6.2.0", "5.4.1"]
    result = runner.invoke(app, ["server", "status"])
    assert result.exit_code == 0
    assert "6.2.0" in result.output
    assert "5.4.1" in result.output


def test_ping_top_level_alias(config_path, a_server, client_mock, runner):
    """Ping works as a top-level alias for server status."""
    Config.load().add_server(a_server)
    client_mock.server_version.return_value = "6.2.0"
    result = runner.invoke(app, ["ping", "local"])
    assert result.exit_code == 0
    assert "Version:  6.2.0" in result.output
