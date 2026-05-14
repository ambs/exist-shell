"""Tests for the sync command."""

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

from exist_shell.commands.sync import Manifest
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
    manifest_path.write_text(json.dumps({
        "doc.xml": {"local_sha256": _sha256(b"<original/>"), "remote_last_modified": "2025-01-01T00:00:00.000"}
    }))

    # Remote has a different mtime → remote was also changed
    client_mock.list_collection.return_value = [_resource("doc.xml", "2025-06-01T00:00:00.000")]

    result = runner.invoke(app, ["sync", str(local_dir), "myapp:/"])
    assert result.exit_code == 0
    client_mock.put_document.assert_not_called()
    assert "! doc.xml  (conflict: modified on both sides, skipping)" in result.output


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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
    manifest_key = hashlib.sha256(b"/").hexdigest()[:16]
    manifest_path = manifest_dir / f"myapp@{manifest_key}.json"
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
