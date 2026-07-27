"""Tests for the cp command."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app
from exist_shell.models import DocumentResult


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the cp command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.cp.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def xml_doc():
    """A minimal XML document returned by the server."""
    return DocumentResult(content=b"<root/>", mime_type="application/xml")


# --- local → remote ---

def test_local_to_remote_exact_path(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    result = runner.invoke(app, ["cp", str(f), "myapp:/docs/doc.xml"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once_with(
        "/db/myapp/docs/doc.xml", b"<root/>", "application/xml"
    )


def test_local_to_remote_into_directory(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "doc.xml"
    f.write_bytes(b"<root/>")
    result = runner.invoke(app, ["cp", str(f), "myapp:/docs/"])
    assert result.exit_code == 0
    path_arg = client_mock.put_document.call_args[0][0]
    assert path_arg == "/db/myapp/docs/doc.xml"


def test_local_to_remote_guesses_mime(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "image.png"
    f.write_bytes(b"\x89PNG")
    result = runner.invoke(app, ["cp", str(f), "myapp:/images/image.png"])
    assert result.exit_code == 0
    _, _, mime = client_mock.put_document.call_args[0]
    assert mime == "image/png"


def test_local_to_remote_unreadable_source_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["cp", "/nonexistent/file.xml", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "cannot read" in result.output


def test_local_to_remote_rejects_malformed_xml(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "bad.xml"
    f.write_bytes(b"<unclosed>")
    result = runner.invoke(app, ["cp", str(f), "myapp:/bad.xml"])
    assert result.exit_code == 1
    assert "not well-formed XML" in result.output
    client_mock.put_document.assert_not_called()


def test_local_to_remote_non_xml_mime_skips_validation(config_with_collection, client_mock, tmp_path, runner):
    f = tmp_path / "data.bin"
    f.write_bytes(b"\x00\x01\x02not xml")
    result = runner.invoke(app, ["cp", str(f), "myapp:/data.bin"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()


# --- remote → local ---

def test_remote_to_local_exact_path(config_with_collection, client_mock, xml_doc, tmp_path, runner):
    client_mock.get_document.return_value = xml_doc
    dest = tmp_path / "out.xml"
    result = runner.invoke(app, ["cp", "myapp:/docs/doc.xml", str(dest)])
    assert result.exit_code == 0
    assert dest.read_bytes() == b"<root/>"


def test_remote_to_local_into_directory(config_with_collection, client_mock, xml_doc, tmp_path, runner):
    client_mock.get_document.return_value = xml_doc
    result = runner.invoke(app, ["cp", "myapp:/docs/doc.xml", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / "doc.xml").read_bytes() == b"<root/>"


def test_remote_to_local_not_found_fails(config_with_collection, client_mock, tmp_path, runner):
    client_mock.get_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["cp", "myapp:/missing.xml", str(tmp_path)])
    assert result.exit_code == 1
    assert "not found" in result.output


# --- remote → remote ---

def test_remote_to_remote_exact_path(config_with_collection, client_mock, xml_doc, runner):
    client_mock.get_document.return_value = xml_doc
    result = runner.invoke(app, ["cp", "myapp:/src/doc.xml", "myapp:/dst/doc.xml"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once_with(
        "/db/myapp/dst/doc.xml", b"<root/>", "application/xml"
    )


def test_remote_to_remote_into_directory(config_with_collection, client_mock, xml_doc, runner):
    client_mock.get_document.return_value = xml_doc
    result = runner.invoke(app, ["cp", "myapp:/src/doc.xml", "myapp:/dst/"])
    assert result.exit_code == 0
    path_arg = client_mock.put_document.call_args[0][0]
    assert path_arg == "/db/myapp/dst/doc.xml"


def test_remote_to_remote_preserves_mime(config_with_collection, client_mock, runner):
    client_mock.get_document.return_value = DocumentResult(
        content=b"\x89PNG", mime_type="image/png"
    )
    result = runner.invoke(app, ["cp", "myapp:/src/img.png", "myapp:/dst/img.png"])
    assert result.exit_code == 0
    _, _, mime = client_mock.put_document.call_args[0]
    assert mime == "image/png"


def test_remote_to_remote_auth_error_on_get_fails(config_with_collection, client_mock, runner):
    client_mock.get_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["cp", "myapp:/src/doc.xml", "myapp:/dst/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_remote_to_remote_connection_error_on_put_fails(config_with_collection, client_mock, xml_doc, runner):
    client_mock.get_document.return_value = xml_doc
    client_mock.put_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["cp", "myapp:/src/doc.xml", "myapp:/dst/doc.xml"])
    assert result.exit_code == 1


# --- both local ---

def test_both_local_fails(config_path, runner):
    result = runner.invoke(app, ["cp", "/local/src.xml", "/local/dst.xml"])
    assert result.exit_code == 1
    assert "remote" in result.output


# --- path validation ---

def test_cp_rejects_traversal_in_source(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["cp", "myapp:/../other.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_cp_rejects_traversal_in_target(config_with_collection, client_mock, xml_doc, runner):
    client_mock.get_document.return_value = xml_doc
    result = runner.invoke(app, ["cp", "myapp:/src.xml", "myapp:/../other.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output
