"""Tests for the put command."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from exist_shell.commands.put import _resolve_mime
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the put command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.put.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


# --- _resolve_mime unit tests ---

def test_resolve_mime_explicit_overrides_all():
    assert _resolve_mime(Path("doc.xml"), "--mime image/png") == "--mime image/png"


def test_resolve_mime_guesses_from_extension(tmp_path):
    f = tmp_path / "image.png"
    assert _resolve_mime(f, None) == "image/png"


def test_resolve_mime_unknown_extension_falls_back(tmp_path):
    f = tmp_path / "file.xyzunknown"
    assert _resolve_mime(f, None) == "application/octet-stream"


def test_resolve_mime_stdin_defaults_to_xml():
    assert _resolve_mime(None, None) == "application/xml"


# --- command tests ---

def test_put_from_file(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    result = runner.invoke(app, ["put", "myapp:/doc.xml", "-f", str(f)])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once_with("/db/myapp/doc.xml", b"<root/>", "application/xml")


def test_put_from_file_guesses_mime(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG")
    result = runner.invoke(app, ["put", "myapp:/image.png", "-f", str(f)])
    assert result.exit_code == 0
    _, _, resolved_mime = client_mock.put_document.call_args[0]
    assert resolved_mime == "image/png"


def test_put_explicit_mime_overrides_guess(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG")
    result = runner.invoke(app, ["put", "myapp:/image.png", "-f", str(f), "--mime", "image/jpeg"])
    assert result.exit_code == 0
    _, _, resolved_mime = client_mock.put_document.call_args[0]
    assert resolved_mime == "image/jpeg"


def test_put_missing_path_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["put", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_put_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["put", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_put_not_found_fails(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    client_mock.put_document.side_effect = ExistNotFoundError("/db/myapp/missing/doc.xml")
    result = runner.invoke(app, ["put", "myapp:/missing/doc.xml", "-f", str(f)])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_put_auth_error_fails(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    client_mock.put_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["put", "myapp:/doc.xml", "-f", str(f)])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_put_connection_error_fails(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    client_mock.put_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["put", "myapp:/doc.xml", "-f", str(f)])
    assert result.exit_code == 1


def test_put_unreadable_file_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["put", "myapp:/doc.xml", "-f", "/nonexistent/path/doc.xml"])
    assert result.exit_code == 1
    assert "cannot read" in result.output
