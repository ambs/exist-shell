from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app
from exist_shell.models import CollectionEntry, ResourceEntry


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.ls.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def items():
    return [
        CollectionEntry(name="subdir", permissions="rwxr-xr-x", owner="admin"),
        ResourceEntry(name="file.xml", size=1234, mime_type="application/xml"),
    ]


def test_ls_lists_subcollection(config_with_collection, client_mock, items, runner):
    client_mock.list_collection.return_value = items
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 0
    assert "subdir/" in result.output


def test_ls_lists_resource(config_with_collection, client_mock, items, runner):
    client_mock.list_collection.return_value = items
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 0
    assert "file.xml" in result.output


def test_ls_default_path_is_root(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = []
    runner.invoke(app, ["ls", "myapp"])
    client_mock.list_collection.assert_called_once_with("/db/myapp/")


def test_ls_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["ls", "ghost:/"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_ls_not_found_path_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistNotFoundError("/db/myapp/missing")
    result = runner.invoke(app, ["ls", "myapp:/missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_ls_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 1


def test_ls_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 1


def test_ls_rejects_path_traversal(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["ls", "myapp:/../other"])
    assert result.exit_code == 1
    assert "traversal" in result.output
