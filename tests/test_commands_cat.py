"""Tests for the cat command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app
from exist_shell.models import DocumentResult


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the cat command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.cat.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


def test_cat_prints_text(config_with_collection, client_mock, runner):
    client_mock.get_document.return_value = DocumentResult(
        content=b"<root/>", mime_type="application/xml"
    )
    result = runner.invoke(app, ["cat", "myapp:/doc.xml"])
    assert result.exit_code == 0
    assert "<root/>" in result.output


def test_cat_binary_without_raw_fails(config_with_collection, client_mock, runner):
    client_mock.get_document.return_value = DocumentResult(
        content=b"\x00\x01\x02", mime_type="application/octet-stream"
    )
    result = runner.invoke(app, ["cat", "myapp:/image.png"])
    assert result.exit_code == 1
    assert "binary" in result.output


def test_cat_binary_with_raw_succeeds(config_with_collection, client_mock, runner):
    client_mock.get_document.return_value = DocumentResult(
        content=b"\x00\x01\x02", mime_type="application/octet-stream"
    )
    result = runner.invoke(app, ["cat", "--raw", "myapp:/image.png"], catch_exceptions=False)
    assert result.exit_code == 0


def test_cat_missing_path_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["cat", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_cat_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["cat", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_cat_not_found_fails(config_with_collection, client_mock, runner):
    client_mock.get_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["cat", "myapp:/missing.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_cat_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.get_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["cat", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_cat_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.get_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["cat", "myapp:/doc.xml"])
    assert result.exit_code == 1
