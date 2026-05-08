from unittest.mock import MagicMock

import pytest

from exist_shell.config import Collection, Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.server.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_server_ls_empty(config_path, runner):
    result = runner.invoke(app, ["server", "ls"])
    assert result.exit_code == 0
    assert result.output == ""


def test_server_ls_lists_servers(config_path, a_server, runner):
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "ls"])
    assert result.exit_code == 0
    assert "local" in result.output
    assert "localhost:8080" in result.output


def test_server_add_success(config_path, client_mock, runner):
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 0
    assert "localhost" in Config.load().servers


def test_server_add_uses_custom_nick(config_path, client_mock, runner):
    result = runner.invoke(app, ["server", "add", "myserver.example.com", "--nick", "prod"], input="\n")
    assert result.exit_code == 0
    assert "prod" in Config.load().servers


def test_server_add_duplicate_nick_fails(config_path, a_server, client_mock, runner):
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "add", "localhost", "--nick", "local"], input="\n")
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_server_add_connection_error_fails(config_path, client_mock, runner):
    client_mock.check_connection.side_effect = ExistConnectionError("http://localhost:8080/exist/rest/db", Exception("refused"))
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 1
    assert "localhost" not in Config.load().servers


def test_server_add_auth_error_fails(config_path, client_mock, runner):
    client_mock.check_connection.side_effect = ExistAuthError("http://localhost:8080/exist/rest/db")
    result = runner.invoke(app, ["server", "add", "localhost"], input="\n")
    assert result.exit_code == 1
    assert "localhost" not in Config.load().servers


# ---------------------------------------------------------------------------
# server rm
# ---------------------------------------------------------------------------


def test_server_rm_removes_server(config_path, a_server, runner):
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rm", "local"])
    assert result.exit_code == 0
    assert "local" not in Config.load().servers
    assert "removed" in result.output


def test_server_rm_unknown_nick_fails(config_path, runner):
    result = runner.invoke(app, ["server", "rm", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_server_rm_cascades_collections(config_path, a_server, runner):
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
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed 1 collection: myapp" in result.output


def test_server_rm_cascade_message_plural(config_path, a_server, runner):
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="other", server_nick="local", name="other"))
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed 2 collections:" in result.output


def test_server_rm_no_cascade_message_when_no_collections(config_path, a_server, runner):
    Config.load().add_server(a_server)
    result = runner.invoke(app, ["server", "rm", "local"])
    assert "Also removed" not in result.output


def test_server_rm_keeps_other_server_collections(config_path, a_server, runner):
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
    Config.load().add_server(a_server)
    runner.invoke(app, ["server", "rm", "local"])
    client_mock.check_connection.assert_not_called()
