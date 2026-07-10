"""Tests for the find command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the find command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.find.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_find_lists_matches(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = ["/db/myapp/a.xml", "/db/myapp/b.xml"]
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]'])
    assert result.exit_code == 0
    assert "myapp:/a.xml" in result.output
    assert "myapp:/b.xml" in result.output
    client_mock.find_documents.assert_called_once_with("/db/myapp/", 'foo[@type="draft"]')
    client_mock.delete_document.assert_not_called()


def test_find_no_matches_prints_nothing(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = []
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]'])
    assert result.exit_code == 0
    assert result.output == ""


def test_find_remove_with_yes_deletes_and_prints(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = ["/db/myapp/a.xml"]
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]', "--remove", "--yes"])
    assert result.exit_code == 0
    assert "myapp:/a.xml" in result.output
    client_mock.delete_document.assert_called_once_with("/db/myapp/a.xml")


def test_find_remove_confirms_interactively(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = ["/db/myapp/a.xml"]
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]', "--remove"], input="y\n")
    assert result.exit_code == 0
    client_mock.delete_document.assert_called_once_with("/db/myapp/a.xml")


def test_find_remove_abort_on_no(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = ["/db/myapp/a.xml"]
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]', "--remove"], input="n\n")
    assert result.exit_code != 0
    client_mock.delete_document.assert_not_called()


def test_find_remove_no_matches_skips_prompt(config_with_collection, client_mock, runner):
    client_mock.find_documents.return_value = []
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]', "--remove"])
    assert result.exit_code == 0
    client_mock.delete_document.assert_not_called()


def test_find_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["find", "ghost:/", "--query", 'foo[@type="draft"]'])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_find_query_error_exits_1(config_with_collection, client_mock, runner):
    client_mock.find_documents.side_effect = ExistQueryError("Unexpected token")
    result = runner.invoke(app, ["find", "myapp:/", "--query", "invalid !!!"])
    assert result.exit_code == 1
    assert "XQuery error" in result.output


def test_find_auth_error_exits_1(config_with_collection, client_mock, runner):
    client_mock.find_documents.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]'])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_find_connection_error_exits_1(config_with_collection, client_mock, runner):
    client_mock.find_documents.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["find", "myapp:/", "--query", 'foo[@type="draft"]'])
    assert result.exit_code == 1


def test_find_missing_query_option_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["find", "myapp:/"])
    assert result.exit_code != 0
    client_mock.find_documents.assert_not_called()
