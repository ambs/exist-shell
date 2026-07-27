"""Tests for the edit command."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app
from exist_shell.models import DocumentResult


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the edit command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.edit.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def xml_doc():
    """A minimal XML document returned by the server."""
    return DocumentResult(content=b"<root/>", mime_type="application/xml")


def _editor_that_writes(new_content: bytes):
    """Return a subprocess.run mock that writes new_content to the temp file."""
    def _run(args, **kwargs):
        Path(args[-1]).write_bytes(new_content)
        return subprocess.CompletedProcess(args, 0)
    return _run


def _editor_noop():
    """Return a subprocess.run mock that leaves the temp file unchanged."""
    def _run(args, **kwargs):
        return subprocess.CompletedProcess(args, 0)
    return _run


def _editor_fails():
    """Return a subprocess.run mock that simulates an editor error."""
    def _run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1)
    return _run


# --- happy path ---

def test_edit_uploads_changes(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit uploads changes."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")
    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor_that_writes(b"<modified/>")):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once_with(
        "/db/myapp/doc.xml", b"<modified/>", "application/xml"
    )


def test_edit_skips_upload_when_unchanged(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit skips upload when unchanged."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")
    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor_noop()):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 0
    assert "No changes" in result.output
    client_mock.put_document.assert_not_called()


def test_edit_temp_file_has_correct_suffix(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit temp file has correct suffix."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")
    seen_suffix = []

    def _capture(args, **kwargs):
        seen_suffix.append(Path(args[-1]).suffix)
        return subprocess.CompletedProcess(args, 0)

    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_capture):
        runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert seen_suffix == [".xml"]


def test_edit_uses_visual_env(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit uses visual env."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "myeditor")
    seen_cmd = []

    def _capture(args, **kwargs):
        seen_cmd.append(args[0])
        return subprocess.CompletedProcess(args, 0)

    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_capture):
        runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert seen_cmd == ["myeditor"]


def test_edit_falls_back_to_editor_env(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit falls back to editor env."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.setenv("EDITOR", "nano")
    seen_cmd = []

    def _capture(args, **kwargs):
        seen_cmd.append(args[0])
        return subprocess.CompletedProcess(args, 0)

    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_capture):
        runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert seen_cmd == ["nano"]


def test_find_editor_falls_back_to_notepad_on_windows(monkeypatch):
    """Find editor falls back to notepad on windows."""
    from exist_shell.commands.edit import _find_editor

    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert _find_editor() == "notepad"


# --- error paths ---

def test_edit_editor_nonzero_exit_fails(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit editor nonzero exit fails."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")
    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor_fails()):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "editor exited" in result.output
    client_mock.put_document.assert_not_called()


def test_edit_missing_path_fails(config_with_collection, client_mock, runner):
    """Edit missing path fails."""
    result = runner.invoke(app, ["edit", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_edit_unknown_collection_fails(config_path, client_mock, runner):
    """Edit unknown collection fails."""
    result = runner.invoke(app, ["edit", "ghost:/doc.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_edit_rejects_path_traversal(config_with_collection, client_mock, runner):
    """Edit rejects path traversal."""
    result = runner.invoke(app, ["edit", "myapp:/../other/secret.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_edit_not_found_fails(config_with_collection, client_mock, runner):
    """Edit not found fails."""
    client_mock.get_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["edit", "myapp:/missing.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_edit_auth_error_on_get_fails(config_with_collection, client_mock, runner):
    """Edit auth error on get fails."""
    client_mock.get_document.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_edit_connection_error_on_get_fails(config_with_collection, client_mock, runner):
    """Edit connection error on get fails."""
    client_mock.get_document.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 1


def test_edit_auth_error_on_put_fails(config_with_collection, client_mock, xml_doc, runner, monkeypatch):
    """Edit auth error on put fails."""
    client_mock.get_document.return_value = xml_doc
    client_mock.put_document.side_effect = ExistAuthError("url")
    monkeypatch.setenv("VISUAL", "vi")
    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor_that_writes(b"<changed/>")):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


# --- XML well-formedness ---

def test_edit_warns_on_malformed_xml_and_reopens_editor(
    config_with_collection, client_mock, xml_doc, runner, monkeypatch
):
    """Editor writes bad XML first, then valid XML — should warn, re-open, and upload."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")

    call_count = 0

    def _editor(args, **kwargs):
        nonlocal call_count
        path = Path(args[-1])
        if call_count == 0:
            path.write_bytes(b"<broken")
        else:
            path.write_bytes(b"<fixed/>")
        call_count += 1
        return subprocess.CompletedProcess(args, 0)

    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"], input="\n")

    assert result.exit_code == 0
    assert "not well-formed XML" in result.output
    assert "Press Enter" in result.output
    client_mock.put_document.assert_called_once_with("/db/myapp/doc.xml", b"<fixed/>", "application/xml")


def test_edit_aborts_when_user_abandons_malformed_xml(
    config_with_collection, client_mock, xml_doc, runner, monkeypatch
):
    """Editor writes bad XML, then saves without changes on retry — should abort."""
    client_mock.get_document.return_value = xml_doc
    monkeypatch.setenv("VISUAL", "vi")

    call_count = 0

    def _editor(args, **kwargs):
        nonlocal call_count
        if call_count == 0:
            Path(args[-1]).write_bytes(b"<broken")
        # second call: leave the file unchanged (simulate user quitting)
        call_count += 1
        return subprocess.CompletedProcess(args, 0)

    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor):
        result = runner.invoke(app, ["edit", "myapp:/doc.xml"], input="\n")

    assert result.exit_code == 1
    assert "still has XML errors" in result.output
    client_mock.put_document.assert_not_called()



def test_edit_non_xml_mime_skips_validation(
    config_with_collection, client_mock, runner, monkeypatch
):
    """Binary document — malformed-as-XML bytes should pass through unchecked."""
    doc = DocumentResult(content=b"\x89PNG", mime_type="image/png")
    client_mock.get_document.return_value = doc
    monkeypatch.setenv("VISUAL", "vi")
    with patch("exist_shell.commands.edit.subprocess.run", side_effect=_editor_that_writes(b"\x89PNG\x00")):
        result = runner.invoke(app, ["edit", "myapp:/image.png"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()
