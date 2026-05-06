from unittest.mock import MagicMock

import pytest

from exist_shell.config import Config
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
