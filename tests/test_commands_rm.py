"""Tests for the rm command."""

from unittest.mock import MagicMock, patch

import pytest

import exist_shell.commands.rm as rm_module
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the rm command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.rm.ExistClient", lambda _: mock)
    client = mock.__enter__.return_value
    client.is_collection.return_value = False
    return client


def test_rm_deletes_document(config_with_collection, client_mock, runner):
    """Rm deletes document."""
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.delete_document.assert_called_once_with("/db/myapp/doc.xml")


def test_rm_multiple_targets(config_with_collection, client_mock, runner):
    """Rm multiple targets."""
    result = runner.invoke(app, ["rm", "myapp:/a.xml", "myapp:/b.xml"])
    assert result.exit_code == 0
    assert client_mock.delete_document.call_count == 2


def test_rm_missing_path_fails(config_with_collection, client_mock, runner):
    """Rm missing path fails."""
    result = runner.invoke(app, ["rm", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_rm_unknown_collection_fails(config_path, client_mock, runner):
    """Rm unknown collection fails."""
    result = runner.invoke(app, ["rm", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_rm_not_found_fails(config_with_collection, client_mock, runner):
    """Rm not found fails."""
    client_mock.delete_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["rm", "myapp:/missing.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_rm_auth_error_fails(config_with_collection, client_mock, runner):
    """Rm auth error fails."""
    client_mock.delete_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_rm_connection_error_fails(config_with_collection, client_mock, runner):
    """Rm connection error fails."""
    client_mock.delete_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 1


def test_rm_rejects_path_traversal(config_with_collection, client_mock, runner):
    """Rm rejects path traversal."""
    result = runner.invoke(app, ["rm", "myapp:/../secret.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_rm_invalidates_cache_after_document_delete(config_with_collection, client_mock, runner):
    """Rm invalidates cache after document delete."""
    with patch.object(rm_module, "invalidate") as mock_invalidate:
        result = runner.invoke(app, ["rm", "myapp:/doc.xml"])
    assert result.exit_code == 0
    mock_invalidate.assert_called_once_with("myapp")


def test_rm_refuses_collection_without_recursive(config_with_collection, client_mock, runner):
    """Rm refuses collection without recursive."""
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["rm", "myapp:/reports"])
    assert result.exit_code == 1
    assert "is a collection" in result.output
    assert "--recursive" in result.output
    client_mock.delete_document.assert_not_called()
    client_mock.delete_collection.assert_not_called()


def test_rm_recursive_deletes_collection_after_confirmation(config_with_collection, client_mock, runner):
    """Rm recursive deletes collection after confirmation."""
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["rm", "--recursive", "myapp:/reports"], input="y\n")
    assert result.exit_code == 0
    client_mock.delete_collection.assert_called_once_with("/db/myapp/reports")


def test_rm_recursive_aborts_when_confirmation_declined(config_with_collection, client_mock, runner):
    """Rm recursive aborts when confirmation declined."""
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["rm", "--recursive", "myapp:/reports"], input="n\n")
    assert result.exit_code != 0
    client_mock.delete_collection.assert_not_called()


def test_rm_recursive_yes_skips_confirmation(config_with_collection, client_mock, runner):
    """Rm recursive yes skips confirmation."""
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["rm", "-r", "-y", "myapp:/reports"])
    assert result.exit_code == 0
    client_mock.delete_collection.assert_called_once_with("/db/myapp/reports")


def test_rm_recursive_invalidates_cache_after_collection_delete(config_with_collection, client_mock, runner):
    """Rm recursive invalidates cache after collection delete."""
    client_mock.is_collection.return_value = True
    with patch.object(rm_module, "invalidate") as mock_invalidate:
        result = runner.invoke(app, ["rm", "-r", "-y", "myapp:/reports"])
    assert result.exit_code == 0
    mock_invalidate.assert_called_once_with("myapp")
