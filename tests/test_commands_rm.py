"""Tests for the rm command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the rm command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.rm.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_rm_deletes_document(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.delete_document.assert_called_once_with("/db/myapp/doc.xml")


def test_rm_multiple_targets(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["rm", "myapp:/a.xml", "myapp:/b.xml"])
    assert result.exit_code == 0
    assert client_mock.delete_document.call_count == 2


def test_rm_missing_path_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["rm", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_rm_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["rm", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_rm_not_found_fails(config_with_collection, client_mock, runner):
    client_mock.delete_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["rm", "myapp:/missing.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_rm_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.delete_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_rm_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.delete_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 1


def test_rm_rejects_path_traversal(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["rm", "myapp:/../secret.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output
