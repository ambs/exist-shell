from unittest.mock import MagicMock

import pytest

from exist_shell.config import Collection, Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.collection.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_with_server(config_path, a_server):
    Config.load().add_server(a_server)


def test_collection_ls_empty(config_path, runner):
    result = runner.invoke(app, ["collection", "ls"])
    assert result.exit_code == 0
    assert result.output == ""


def test_collection_ls_lists_collections(config_path, a_server, runner):
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    result = runner.invoke(app, ["collection", "ls"])
    assert result.exit_code == 0
    assert "myapp" in result.output
    assert "/db/myapp" in result.output
    assert "@local" in result.output


def test_collection_add_success(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = True
    result = runner.invoke(app, ["collection", "add", "myapp", "--server", "local"])
    assert result.exit_code == 0
    assert "myapp" in Config.load().collections


def test_collection_add_auto_selects_single_server(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = True
    result = runner.invoke(app, ["collection", "add", "myapp"])
    assert result.exit_code == 0
    assert Config.load().collections["myapp"].server_nick == "local"


def test_collection_add_requires_server_when_multiple(config_path, client_mock, runner, a_server):
    from pydantic import SecretStr
    from exist_shell.config import Server
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    result = runner.invoke(app, ["collection", "add", "myapp"])
    assert result.exit_code == 1
    assert "--server" in result.output


def test_collection_add_unknown_server_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["collection", "add", "myapp", "--server", "ghost"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_collection_add_duplicate_nick_fails(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = True
    runner.invoke(app, ["collection", "add", "myapp", "--server", "local"])
    result = runner.invoke(app, ["collection", "add", "myapp", "--server", "local"])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_collection_add_collection_not_found_fails(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = False
    result = runner.invoke(app, ["collection", "add", "ghost", "--server", "local"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_collection_add_connection_error_fails(config_with_server, client_mock, runner):
    client_mock.collection_exists.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["collection", "add", "myapp", "--server", "local"])
    assert result.exit_code == 1
    assert "myapp" not in Config.load().collections


def test_collection_add_auth_error_fails(config_with_server, client_mock, runner):
    client_mock.collection_exists.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["collection", "add", "myapp", "--server", "local"])
    assert result.exit_code == 1


def test_collection_add_at_syntax(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = True
    result = runner.invoke(app, ["collection", "add", "myapp@local"])
    assert result.exit_code == 0
    assert "myapp" in Config.load().collections


def test_collection_add_at_syntax_conflict_fails(config_with_server, client_mock, runner):
    result = runner.invoke(app, ["collection", "add", "myapp@local", "--server", "other"])
    assert result.exit_code == 1
    assert "conflicting" in result.output


def test_collection_add_at_syntax_matching_server_option_ok(config_with_server, client_mock, runner):
    client_mock.collection_exists.return_value = True
    result = runner.invoke(app, ["collection", "add", "myapp@local", "--server", "local"])
    assert result.exit_code == 0
