"""Tests for the sync command."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from exist_shell.commands.sync import Manifest, _manifest_path
from exist_shell.exceptions import ExistAuthError, ExistConnectionError
from exist_shell.main import app
from exist_shell.models import DocumentResult, ResourceEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resource(name: str, mtime: str = "2025-01-01T00:00:00.000", size: int = 10) -> ResourceEntry:
    return ResourceEntry(name=name, last_modified=mtime, size=size)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the sync command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.sync.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def manifest_dir(tmp_path, monkeypatch):
    """Redirect the sync manifest cache to a temp directory."""
    sync_dir = tmp_path / "sync"
    monkeypatch.setattr("exist_shell.commands.sync._get_sync_cache_dir", lambda: sync_dir)
    return sync_dir


@pytest.fixture
def local_dir(tmp_path) -> Path:
    """An empty local directory to use as sync source/destination."""
    d = tmp_path / "local"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Push — basic file decisions
# ---------------------------------------------------------------------------

def test_push_uploads_new_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    content = b"<root/>"
    (local_dir / "doc.xml").write_bytes(content)
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()
    assert "↑ doc.xml  (new)" in result.output


def test_push_skips_unchanged_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    content = b"<root/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(content)

    mtime = "2025-01-01T00:00:00.000"
    manifest_dir.mkdir(parents=True)
    # Write a manifest that matches current local state
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(content), "remote_last_modified": mtime}
    }))

    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "= doc.xml  (unchanged)" not in result.output

    result = runner.invoke(app, ["sync", "--verbose", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    assert "= doc.xml  (unchanged)" in result.output


def test_push_uploads_modified_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    old_content = b"<old/>"
    new_content = b"<new/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(new_content)

    mtime = "2025-01-01T00:00:00.000"
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(old_content), "remote_last_modified": mtime}
    }))

    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()
    assert "↑ doc.xml  (modified)" in result.output


def test_push_detects_conflict(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(b"<local/>")

    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<original/>"), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    # Remote has a different mtime → remote was also changed
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "! doc.xml  (conflict: modified on both sides, skipping)" in result.output


def test_push_manifest_not_shared_across_local_dirs(
    config_with_collection, client_mock, manifest_dir, local_dir, tmp_path, runner
):
    """Regression test for #137: a second local dir must not inherit another dir's manifest state."""
    # State left behind by a previous sync of `local_dir` against an older remote mtime.
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<a/>"), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    # A second, independent local directory that has never been synced before.
    other_dir = tmp_path / "other_local"
    other_dir.mkdir()
    (other_dir / "doc.xml").write_bytes(b"<b/>")

    # Remote mtime has since moved on from what's recorded for `local_dir`.
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", str(other_dir), "myapp:/"])
    assert result.exit_code == 0
    # Must be a plain unconditional upload (no manifest entry for this dir),
    # not a false conflict against local_dir's unrelated recorded state.
    client_mock.put_document.assert_called_once()
    assert "conflict" not in result.output


def test_push_force_uploads_all(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    content = b"<root/>"
    (local_dir / "a.xml").write_bytes(content)
    (local_dir / "b.xml").write_bytes(content)
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--force", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    assert client_mock.put_document.call_count == 2


def test_push_dry_run_does_not_upload(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "doc.xml").write_bytes(b"<root/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--dry-run", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "↑ doc.xml  (new)" in result.output


# ---------------------------------------------------------------------------
# Push — directory and delete
# ---------------------------------------------------------------------------

def test_push_creates_missing_remote_collection(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    subdir = local_dir / "reports"
    subdir.mkdir()
    (subdir / "doc.xml").write_bytes(b"<r/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.create_collection.assert_called_once()
    assert "+ reports/  (new collection)" in result.output


def test_push_delete_removes_remote_extra(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    # Local dir is empty; remote has a file that should be deleted
    client_mock.list_collection.return_value = [_resource("old.xml")]

    result = runner.invoke(app, ["sync", "--delete", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.delete_document.assert_called_once()
    assert "✗ old.xml  (deleted)" in result.output


def test_push_delete_removes_empty_remote_collection(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    from exist_shell.models import CollectionEntry

    empty_col = CollectionEntry(name="archive")
    # _walk_remote recurses: each call to list_collection on the base is followed
    # by a recursive call into each CollectionEntry found there.
    # Sequence:
    #   1. initial _walk_remote: base → [archive col + old.xml]
    #   2. initial _walk_remote: recurse into archive → []
    #   3. _delete_empty_remote_dirs _walk_remote: base → [archive col] (file gone)
    #   4. _delete_empty_remote_dirs _walk_remote: recurse into archive → []
    client_mock.list_collection.side_effect = [
        [empty_col, _resource("old.xml")],
        [],
        [empty_col],
        [],
    ]

    result = runner.invoke(app, ["sync", "--delete", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.delete_collection.assert_called_once()
    assert "✗ archive/  (empty collection deleted)" in result.output


def test_push_no_delete_leaves_remote_extra(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.return_value = [_resource("old.xml")]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.delete_document.assert_not_called()


# ---------------------------------------------------------------------------
# Pull — basic file decisions
# ---------------------------------------------------------------------------

def test_pull_downloads_new_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.return_value = [_resource("doc.xml")]
    client_mock.get_document.return_value = DocumentResult(b"<root/>", "application/xml")

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert (local_dir / "doc.xml").exists()
    assert "↓ doc.xml  (new)" in result.output


def test_pull_skips_unchanged_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    content = b"<root/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(content)

    mtime = "2025-01-01T00:00:00.000"
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(content), "remote_last_modified": mtime}
    }))

    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    client_mock.get_document.assert_not_called()
    assert "= doc.xml  (unchanged)" not in result.output

    result = runner.invoke(app, ["sync", "--verbose", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert "= doc.xml  (unchanged)" in result.output


def test_pull_downloads_missing_local_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    # Manifest says file is synced but local file was deleted — must re-download.
    mtime = "2025-01-01T00:00:00.000"
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<root/>"), "remote_last_modified": mtime}
    }))

    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]
    client_mock.get_document.return_value = DocumentResult(b"<root/>", "application/xml")

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    client_mock.get_document.assert_called_once()
    assert (local_dir / "doc.xml").exists()
    assert "↓ doc.xml  (modified)" in result.output


def test_pull_downloads_modified_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    content = b"<old/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(content)

    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(content), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]
    client_mock.get_document.return_value = DocumentResult(b"<new/>", "application/xml")

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    client_mock.get_document.assert_called_once()
    assert "↓ doc.xml  (modified)" in result.output


def test_pull_detects_conflict(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(b"<local_edit/>")

    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<original/>"), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    # Remote mtime changed AND local file also changed from original
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    client_mock.get_document.assert_not_called()
    assert "! doc.xml  (conflict: modified on both sides, skipping)" in result.output


def test_pull_force_downloads_all(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.return_value = [_resource("a.xml"), _resource("b.xml")]
    client_mock.get_document.return_value = DocumentResult(b"<x/>", "application/xml")

    result = runner.invoke(app, ["sync", "--force", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert client_mock.get_document.call_count == 2


def test_pull_dry_run_does_not_download(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.return_value = [_resource("doc.xml")]

    result = runner.invoke(app, ["sync", "--dry-run", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    client_mock.get_document.assert_not_called()
    assert "↓ doc.xml  (new)" in result.output


# ---------------------------------------------------------------------------
# Pull — directory and delete
# ---------------------------------------------------------------------------

def test_pull_creates_missing_local_dir(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    from exist_shell.models import CollectionEntry
    col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [
        [col],
        [],  # empty subcollection
    ]

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert (local_dir / "reports").is_dir()
    assert "+ reports/  (new directory)" in result.output


def test_pull_delete_removes_local_extra(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "stale.xml").write_bytes(b"<old/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--delete", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert not (local_dir / "stale.xml").exists()
    assert "✗ stale.xml  (deleted)" in result.output


def test_pull_delete_removes_empty_local_dir(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    empty_subdir = local_dir / "archive"
    empty_subdir.mkdir()
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--delete", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert not empty_subdir.exists()
    assert "✗ archive/  (empty directory deleted)" in result.output


def test_pull_no_delete_leaves_local_extra(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "stale.xml").write_bytes(b"<old/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert (local_dir / "stale.xml").exists()


# ---------------------------------------------------------------------------
# Direction / validation errors
# ---------------------------------------------------------------------------

def test_sync_both_remote_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["sync", "myapp:/a", "myapp:/b"])
    assert result.exit_code == 1
    assert "both" in result.output


def test_sync_both_local_fails(runner, tmp_path):
    result = runner.invoke(app, ["sync", str(tmp_path), str(tmp_path)])
    assert result.exit_code == 1
    assert "remote" in result.output


def test_sync_source_not_a_dir_fails(config_with_collection, client_mock, runner, tmp_path):
    f = tmp_path / "file.xml"
    f.write_bytes(b"<x/>")
    result = runner.invoke(app, ["sync", str(f), "myapp:/"])
    assert result.exit_code == 1
    assert "not a directory" in result.output


def test_sync_unknown_collection_fails(config_path, client_mock, runner, tmp_path):
    d = tmp_path / "src"
    d.mkdir()
    result = runner.invoke(app, ["sync", str(d), "ghost:/"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_sync_auth_error_fails(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_sync_connection_error_fails(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Checkpointing
# ---------------------------------------------------------------------------

def test_push_checkpoints_manifest_periodically(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    for i in range(3):
        (local_dir / f"doc{i}.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []

    write_calls: list[None] = []
    monkeypatch.setattr(Manifest, "_write", lambda *_: write_calls.append(None))

    result = runner.invoke(app, ["sync", "--checkpoint-every", "2", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    # checkpoint after 2nd mutation + final save = 2 writes
    assert len(write_calls) == 2


def test_pull_checkpoints_manifest_periodically(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    from exist_shell.models import DocumentResult

    client_mock.list_collection.return_value = [
        _resource("a.xml"),
        _resource("b.xml"),
        _resource("c.xml"),
    ]
    client_mock.get_document.return_value = DocumentResult(b"<x/>", "application/xml")

    write_calls: list[None] = []
    monkeypatch.setattr(Manifest, "_write", lambda *_: write_calls.append(None))

    result = runner.invoke(app, ["sync", "--checkpoint-every", "2", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    # checkpoint after 2nd mutation + final save = 2 writes
    assert len(write_calls) == 2


def test_push_dry_run_skips_checkpoints(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    for i in range(3):
        (local_dir / f"doc{i}.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []

    write_calls: list[None] = []
    monkeypatch.setattr(Manifest, "_write", lambda *_: write_calls.append(None))

    result = runner.invoke(app, ["sync", "--dry-run", "--checkpoint-every", "1", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    assert len(write_calls) == 0


def test_pull_dry_run_skips_checkpoints(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    client_mock.list_collection.return_value = [_resource("a.xml"), _resource("b.xml")]

    write_calls: list[None] = []
    monkeypatch.setattr(Manifest, "_write", lambda *_: write_calls.append(None))

    result = runner.invoke(app, ["sync", "--dry-run", "--checkpoint-every", "1", "myapp:/", str(local_dir)])
    assert result.exit_code == 0
    assert len(write_calls) == 0


def test_push_resumes_skipping_already_uploaded_file(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """A file uploaded in a prior interrupted run (empty remote mtime) is skipped on restart when local is unchanged."""
    content = b"<root/>"
    (local_dir / "doc.xml").write_bytes(content)

    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(content), "remote_last_modified": ""}
    }))

    # Remote now has the mtime the server assigned during the prior (incomplete) run
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "= doc.xml  (unchanged)" not in result.output

    result = runner.invoke(app, ["sync", "--verbose", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    assert "= doc.xml  (unchanged)" in result.output


def test_push_skips_touched_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    """A file whose mtime changed but whose content is identical must be skipped, not uploaded."""
    content = b"<root/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(content)

    mtime = "2025-01-01T00:00:00.000"
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    stat = local_file.stat()
    manifest_path.write_text(json.dumps({
        "doc.xml": {
            "local_sha256": _sha256(content),
            "remote_last_modified": mtime,
            "local_mtime_ns": stat.st_mtime_ns,
            "local_size": stat.st_size,
        }
    }))

    # Simulate a touch: re-write identical content so mtime advances
    local_file.write_bytes(content)

    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()


# ---------------------------------------------------------------------------
# Push — XML well-formedness
# ---------------------------------------------------------------------------

def test_push_skips_malformed_xml(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "bad.xml").write_bytes(b"<unclosed>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "! bad.xml  (not well-formed XML" in result.output
    assert "1 invalid xml" in result.output



def test_push_non_xml_file_skips_validation(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "image.png").write_bytes(b"\x89PNG\r\n")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()


def test_push_fail_fast_stops_on_first_invalid(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "a.xml").write_bytes(b"<unclosed>")
    (local_dir / "b.xml").write_bytes(b"<valid/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])
    assert result.exit_code == 1
    # Only the first file was processed; the second was never reached
    assert client_mock.put_document.call_count == 0


def test_push_fail_fast_saves_manifest_on_stop(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    """Files uploaded before the failure should be recorded in the manifest."""
    (local_dir / "a.xml").write_bytes(b"<valid/>")
    (local_dir / "b.xml").write_bytes(b"<unclosed>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])
    assert result.exit_code == 1
    # The valid file was uploaded before the failure
    client_mock.put_document.assert_called_once()
    # Manifest directory should exist and contain a saved manifest
    assert any(manifest_dir.rglob("*.json"))


def test_push_fail_fast_exits_zero_when_no_invalid(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "doc.xml").write_bytes(b"<root/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])
    assert result.exit_code == 0


def test_push_fail_fast_stops_on_conflict(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    """--fail-fast should also abort on conflicts, not just XML errors."""
    import hashlib
    import json

    content = b"<local/>"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(content)

    # Manifest records a different hash (simulating prior sync of different content)
    manifest_dir.mkdir(parents=True)
    manifest_path = _manifest_path("myapp", "/", local_dir)
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<original/>"), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    # Remote also changed (different mtime) → conflict
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])
    assert result.exit_code == 1
    assert "conflict" in result.output
    client_mock.put_document.assert_not_called()


# ---------------------------------------------------------------------------
# Interrupt handling
# ---------------------------------------------------------------------------

def test_push_keyboard_interrupt_exits_cleanly(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    (local_dir / "doc.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []
    monkeypatch.setattr(sync_mod, "_push_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 130
    assert "Interrupted." in result.output


def test_pull_keyboard_interrupt_exits_cleanly(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    client_mock.list_collection.return_value = [_resource("doc.xml")]
    monkeypatch.setattr(sync_mod, "_pull_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])

    assert result.exit_code == 130
    assert "Interrupted." in result.output


def test_push_keyboard_interrupt_during_listing_exits_cleanly(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    client_mock.list_collection.side_effect = KeyboardInterrupt

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 130
    assert "Interrupted." in result.output


def test_pull_keyboard_interrupt_during_listing_exits_cleanly(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    client_mock.list_collection.side_effect = KeyboardInterrupt

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])

    assert result.exit_code == 130
    assert "Interrupted." in result.output


def test_push_keyboard_interrupt_saves_manifest(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    (local_dir / "doc.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []
    monkeypatch.setattr(sync_mod, "_push_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 130
    assert any(manifest_dir.rglob("*.json"))


def test_pull_keyboard_interrupt_saves_manifest(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    client_mock.list_collection.return_value = [_resource("doc.xml")]
    monkeypatch.setattr(sync_mod, "_pull_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])

    assert result.exit_code == 130
    assert any(manifest_dir.rglob("*.json"))


def test_push_keyboard_interrupt_dry_run_skips_manifest_save(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    (local_dir / "doc.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []
    monkeypatch.setattr(sync_mod, "_push_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", "--dry-run", str(local_dir), "myapp:/"])

    assert result.exit_code == 130
    assert not manifest_dir.exists() or not any(manifest_dir.rglob("*.json"))


# ---------------------------------------------------------------------------
# Continue past per-file / listing failures (#131)
# ---------------------------------------------------------------------------

def test_pull_continues_past_failed_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    client_mock.list_collection.return_value = [_resource("bad.xml"), _resource("good.xml")]
    client_mock.get_document.side_effect = [
        ExistConnectionError("url", Exception("boom")),
        DocumentResult(b"<x/>", "application/xml"),
    ]

    result = runner.invoke(app, ["sync", "--jobs", "1", "myapp:/", str(local_dir)])

    assert result.exit_code == 1
    assert "! bad.xml  (error:" in result.output
    assert "↓ good.xml  (new)" in result.output
    assert "1 failed" in result.output
    assert (local_dir / "good.xml").exists()
    assert not (local_dir / "bad.xml").exists()
    assert client_mock.get_document.call_count == 2


def test_push_continues_past_failed_file(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    (local_dir / "bad.xml").write_bytes(b"<bad/>")
    (local_dir / "good.xml").write_bytes(b"<good/>")
    client_mock.list_collection.return_value = []
    client_mock.put_document.side_effect = [
        ExistConnectionError("url", Exception("boom")),
        None,
    ]

    result = runner.invoke(app, ["sync", "--jobs", "1", str(local_dir), "myapp:/"])

    assert result.exit_code == 1
    assert "! bad.xml  (error:" in result.output
    assert "↑ good.xml  (new)" in result.output
    assert "1 failed" in result.output
    assert client_mock.put_document.call_count == 2


def test_push_fail_fast_stops_on_transfer_error(config_with_collection, client_mock, manifest_dir, local_dir, runner):
    """--fail-fast should halt on a transfer exception, with clean attribution (no raw traceback)."""
    (local_dir / "a.xml").write_bytes(b"<a/>")
    (local_dir / "b.xml").write_bytes(b"<b/>")
    client_mock.list_collection.return_value = []
    client_mock.put_document.side_effect = ExistConnectionError("url", Exception("boom"))

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "! a.xml  (error:" in result.output
    # second file never reached
    assert client_mock.put_document.call_count == 1


def test_push_walk_remote_continues_past_subcollection_listing_failure(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """A subcollection whose listing fails during the pre-push walk is skipped and counted, but local files still push."""
    from exist_shell.models import CollectionEntry

    (local_dir / "new.xml").write_bytes(b"<new/>")
    ok_col = CollectionEntry(name="ok")
    bad_col = CollectionEntry(name="bad")
    client_mock.list_collection.side_effect = [
        [ok_col, bad_col],
        [],
        ExistConnectionError("url", Exception("boom")),
        [],  # re-walk after upload, to record the server-assigned mtime
    ]

    result = runner.invoke(app, ["sync", "--jobs", "1", str(local_dir), "myapp:/"])

    assert result.exit_code == 1
    assert "! bad  (error:" in result.output
    assert "↑ new.xml  (new)" in result.output
    assert "1 failed" in result.output
    assert client_mock.put_document.call_count == 1


def test_pull_walk_remote_continues_past_subcollection_listing_failure(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """A subcollection whose listing fails is skipped; the rest of the walk continues."""
    from exist_shell.models import CollectionEntry

    ok_col = CollectionEntry(name="ok")
    bad_col = CollectionEntry(name="bad")
    client_mock.list_collection.side_effect = [
        [ok_col, bad_col],
        [_resource("doc.xml")],
        ExistConnectionError("url", Exception("boom")),
    ]
    client_mock.get_document.return_value = DocumentResult(b"<x/>", "application/xml")

    result = runner.invoke(app, ["sync", "--jobs", "1", "myapp:/", str(local_dir)])

    assert result.exit_code == 1
    assert "! bad  (error:" in result.output
    assert "1 failed" in result.output
    assert (local_dir / "ok" / "doc.xml").exists()


def test_pull_walk_remote_root_failure_still_aborts(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """A failure listing the root path itself still aborts the whole run (regression guard)."""
    client_mock.list_collection.side_effect = ExistConnectionError("url", Exception("boom"))

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


# ---------------------------------------------------------------------------
# Parallelism (--jobs)
# ---------------------------------------------------------------------------

def test_push_jobs_flag_accepted(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    (local_dir / "doc.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--jobs", "2", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()


def test_pull_jobs_flag_accepted(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    client_mock.list_collection.return_value = [_resource("doc.xml")]
    client_mock.get_document.return_value = DocumentResult(b"<x/>", "application/xml")

    result = runner.invoke(app, ["sync", "--jobs", "2", "myapp:/", str(local_dir)])

    assert result.exit_code == 0
    client_mock.get_document.assert_called_once()


# ---------------------------------------------------------------------------
# Parallel concurrency
# ---------------------------------------------------------------------------

def test_push_parallel_runs_tasks_concurrently(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """All uploads execute simultaneously: a barrier with JOBS parties proves it."""
    import threading

    JOBS = 4
    barrier = threading.Barrier(JOBS, timeout=5)
    for i in range(JOBS):
        (local_dir / f"doc{i}.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []

    def gated_upload(*_args: object, **_kwargs: object) -> None:
        barrier.wait()

    client_mock.put_document.side_effect = gated_upload

    result = runner.invoke(app, ["sync", "--jobs", str(JOBS), str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    assert client_mock.put_document.call_count == JOBS


def test_pull_parallel_runs_tasks_concurrently(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """All downloads execute simultaneously: a barrier with JOBS parties proves it."""
    import threading

    JOBS = 4
    barrier = threading.Barrier(JOBS, timeout=5)
    client_mock.list_collection.return_value = [_resource(f"doc{i}.xml") for i in range(JOBS)]

    def gated_download(*_args: object, **_kwargs: object) -> DocumentResult:
        barrier.wait()
        return DocumentResult(b"<x/>", "application/xml")

    client_mock.get_document.side_effect = gated_download

    result = runner.invoke(app, ["sync", "--jobs", str(JOBS), "myapp:/", str(local_dir)])

    assert result.exit_code == 0
    assert client_mock.get_document.call_count == JOBS


# ---------------------------------------------------------------------------
# Missing statement coverage
# ---------------------------------------------------------------------------

def test_push_corrupt_manifest_falls_back_to_empty(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    manifest_dir.mkdir(parents=True)
    _manifest_path("myapp", "/", local_dir).write_text("THIS IS NOT JSON")
    (local_dir / "doc.xml").write_bytes(b"<x/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.put_document.assert_called_once()
    assert "↑ doc.xml  (new)" in result.output


def test_push_skips_locally_modified_malformed_xml(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """File in manifest whose local content changed to malformed XML must be rejected."""
    mtime = "2025-01-01T00:00:00.000"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(b"<unclosed>")

    manifest_dir.mkdir(parents=True)
    _manifest_path("myapp", "/", local_dir).write_text(json.dumps({
        "doc.xml": {
            "local_sha256": _sha256(b"<valid/>"),
            "remote_last_modified": mtime,
            "local_mtime_ns": local_file.stat().st_mtime_ns - 1,
            "local_size": len(b"<valid/>"),
        }
    }))
    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "! doc.xml  (not well-formed XML" in result.output


def test_push_delete_skips_remote_collection_with_local_counterpart(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Push --delete does not remove a remote empty collection when a local dir matches it."""
    from exist_shell.models import CollectionEntry

    (local_dir / "reports").mkdir()
    reports_col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [
        [reports_col],   # initial walk: base
        [],              # initial walk: reports/
        [reports_col],   # _delete_empty_remote_dirs re-walk: base
        [],              # _delete_empty_remote_dirs re-walk: reports/
    ]

    result = runner.invoke(app, ["sync", "--delete", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.delete_collection.assert_not_called()


def test_push_delete_skips_remote_collection_with_remaining_resources(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Push --delete leaves a remote collection intact when the re-walk still shows resources inside."""
    from exist_shell.models import CollectionEntry

    reports_col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [
        [reports_col],                       # initial walk: base
        [_resource("server_only.xml")],      # initial walk: reports/
        [reports_col],                       # re-walk: base
        [_resource("server_only.xml")],      # re-walk: reports/ (reflects pre-delete mock state)
    ]

    result = runner.invoke(app, ["sync", "--delete", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.delete_document.assert_called_once()  # the file was deleted
    client_mock.delete_collection.assert_not_called()  # the collection was not deleted


# ---------------------------------------------------------------------------
# Dry-run variants
# ---------------------------------------------------------------------------

def test_push_dry_run_shows_modified_file_without_uploading(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Dry-run push of a locally modified valid file prints the label but skips the upload."""
    mtime = "2025-01-01T00:00:00.000"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(b"<new/>")

    manifest_dir.mkdir(parents=True)
    _manifest_path("myapp", "/", local_dir).write_text(json.dumps({
        "doc.xml": {
            "local_sha256": _sha256(b"<old/>"),
            "remote_last_modified": mtime,
            "local_mtime_ns": local_file.stat().st_mtime_ns - 1,
            "local_size": len(b"<old/>"),
        }
    }))
    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", "--dry-run", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "↑ doc.xml  (modified)" in result.output


def test_push_dry_run_new_subdir_logged_not_created(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Dry-run push logs a new collection but does not call create_collection."""
    subdir = local_dir / "reports"
    subdir.mkdir()
    (subdir / "doc.xml").write_bytes(b"<r/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["sync", "--dry-run", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.create_collection.assert_not_called()
    assert "+ reports/  (new collection)" in result.output


def test_push_skips_creating_collection_already_on_remote(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Push does not call create_collection for a directory that already exists on the remote."""
    from exist_shell.models import CollectionEntry

    subdir = local_dir / "reports"
    subdir.mkdir()
    (subdir / "doc.xml").write_bytes(b"<r/>")
    reports_col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [
        [reports_col],           # initial walk: base → reports/ already present
        [],                      # initial walk: reports/
        [reports_col],           # _refresh_remote_mtimes re-walk: base
        [_resource("doc.xml")],  # _refresh_remote_mtimes re-walk: reports/
    ]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    client_mock.create_collection.assert_not_called()
    client_mock.put_document.assert_called_once()


def test_pull_dry_run_new_subdir_logged_not_created(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Dry-run pull logs a new local directory but does not create it."""
    from exist_shell.models import CollectionEntry

    col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [[col], []]

    result = runner.invoke(app, ["sync", "--dry-run", "myapp:/", str(local_dir)])

    assert result.exit_code == 0
    assert not (local_dir / "reports").exists()
    assert "+ reports/  (new directory)" in result.output


def test_pull_skips_creating_dir_already_existing_locally(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Pull does not print '+ dir/' for subcollections whose local directory already exists."""
    from exist_shell.models import CollectionEntry

    (local_dir / "reports").mkdir()
    col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [[col], [_resource("doc.xml")]]
    client_mock.get_document.return_value = DocumentResult(b"<x/>", "application/xml")

    result = runner.invoke(app, ["sync", "myapp:/", str(local_dir)])

    assert result.exit_code == 0
    assert "+ reports/  (new directory)" not in result.output
    assert (local_dir / "reports" / "doc.xml").exists()


def test_push_fail_fast_skipped_file_emits_no_label(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """--fail-fast sequential path emits no output for an unchanged file without --verbose."""
    mtime = "2025-01-01T00:00:00.000"
    local_file = local_dir / "doc.xml"
    local_file.write_bytes(b"<root/>")
    stat = local_file.stat()

    manifest_dir.mkdir(parents=True)
    _manifest_path("myapp", "/", local_dir).write_text(json.dumps({
        "doc.xml": {
            "local_sha256": _sha256(b"<root/>"),
            "remote_last_modified": mtime,
            "local_mtime_ns": stat.st_mtime_ns,
            "local_size": stat.st_size,
        }
    }))
    client_mock.list_collection.return_value = [_resource("doc.xml", mtime)]

    result = runner.invoke(app, ["sync", "--fail-fast", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    assert "doc.xml" not in result.output


# ---------------------------------------------------------------------------
# Delete — false branches (kept files, dry-run, non-empty dirs)
# ---------------------------------------------------------------------------

def test_push_delete_keeps_remote_files_with_local_counterparts(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Push --delete removes only remote extras; files that have local counterparts are kept."""
    (local_dir / "a.xml").write_bytes(b"<a/>")
    client_mock.list_collection.side_effect = [
        [_resource("a.xml"), _resource("stale.xml")],   # initial walk
        [_resource("a.xml"), _resource("stale.xml")],   # _delete_empty_remote_dirs re-walk
        [_resource("a.xml"), _resource("stale.xml")],   # _refresh_remote_mtimes re-walk
    ]

    result = runner.invoke(app, ["sync", "--delete", str(local_dir), "myapp:/"])

    assert result.exit_code == 0
    assert client_mock.delete_document.call_count == 1
    assert "✗ stale.xml  (deleted)" in result.output


def test_push_delete_dry_run_logs_remote_extras_without_deleting(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Push --delete --dry-run logs remote extras and empty collections but calls no destructive APIs."""
    from exist_shell.models import CollectionEntry

    archive_col = CollectionEntry(name="archive")
    client_mock.list_collection.side_effect = [
        [archive_col, _resource("old.xml")],   # initial walk: base
        [],                                     # initial walk: archive/
        [archive_col, _resource("old.xml")],   # re-walk: base
        [],                                     # re-walk: archive/
    ]

    result = runner.invoke(
        app, ["sync", "--delete", "--dry-run", str(local_dir), "myapp:/"]
    )

    assert result.exit_code == 0
    client_mock.delete_document.assert_not_called()
    client_mock.delete_collection.assert_not_called()
    assert "✗ old.xml  (deleted)" in result.output
    assert "✗ archive/  (empty collection deleted)" in result.output


def test_pull_delete_keeps_files_and_dirs_with_remote_counterparts(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Pull --delete does not remove local files or dirs that have a remote counterpart."""
    from exist_shell.models import CollectionEntry

    (local_dir / "reports").mkdir()
    (local_dir / "reports" / "a.xml").write_bytes(b"<a/>")
    col = CollectionEntry(name="reports")
    client_mock.list_collection.side_effect = [[col], [_resource("a.xml")]]
    client_mock.get_document.return_value = DocumentResult(b"<a/>", "application/xml")

    result = runner.invoke(app, ["sync", "--delete", "myapp:/", str(local_dir)])

    assert result.exit_code == 0
    assert (local_dir / "reports" / "a.xml").exists()
    assert (local_dir / "reports").is_dir()


def test_pull_delete_dry_run_logs_local_extras_without_deleting(
    config_with_collection, client_mock, manifest_dir, local_dir, runner
):
    """Pull --delete --dry-run logs local extras and empty dirs but leaves everything on disk."""
    empty_subdir = local_dir / "archive"
    empty_subdir.mkdir()
    (local_dir / "stale.xml").write_bytes(b"<old/>")
    client_mock.list_collection.return_value = []

    result = runner.invoke(
        app, ["sync", "--delete", "--dry-run", "myapp:/", str(local_dir)]
    )

    assert result.exit_code == 0
    assert (local_dir / "stale.xml").exists()
    assert empty_subdir.exists()
    assert "✗ stale.xml  (deleted)" in result.output
    assert "✗ archive/  (empty directory deleted)" in result.output


def test_pull_keyboard_interrupt_dry_run_skips_manifest_save(
    config_with_collection, client_mock, manifest_dir, local_dir, runner, monkeypatch
):
    import exist_shell.commands.sync as sync_mod

    client_mock.list_collection.return_value = [_resource("doc.xml")]
    monkeypatch.setattr(sync_mod, "_pull_file_task", MagicMock(side_effect=KeyboardInterrupt))

    result = runner.invoke(app, ["sync", "--dry-run", "myapp:/", str(local_dir)])

    assert result.exit_code == 130
    assert not manifest_dir.exists() or not any(manifest_dir.rglob("*.json"))
