"""Tests for the mkdir command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the mkdir command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.mkdir.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_mkdir_creates_collection(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mkdir", "myapp:/newdir"])
    assert result.exit_code == 0
    client_mock.create_collection.assert_called_once_with("/db/myapp/newdir")


def test_mkdir_missing_path_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mkdir", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_mkdir_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["mkdir", "ghost:/newdir"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_mkdir_parent_not_found_fails(config_with_collection, client_mock, runner):
    client_mock.create_collection.side_effect = ExistNotFoundError("/db/myapp/missing/newdir")
    result = runner.invoke(app, ["mkdir", "myapp:/missing/newdir"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_mkdir_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.create_collection.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["mkdir", "myapp:/newdir"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_mkdir_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.create_collection.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["mkdir", "myapp:/newdir"])
    assert result.exit_code == 1


def test_mkdir_rejects_path_traversal(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mkdir", "myapp:/../evil"])
    assert result.exit_code == 1
    assert "traversal" in result.output
