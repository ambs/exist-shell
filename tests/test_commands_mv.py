"""Tests for the mv command."""

from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the mv command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.mv.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def config_two_servers(config_path):
    """Config with two servers on different hosts and a collection on each."""
    config = Config.load()
    config.add_server(Server(nick="local", host="localhost", port=8080, user="admin", password=SecretStr("")))
    config.add_server(Server(nick="other", host="other.host", port=8080, user="admin", password=SecretStr("")))
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="otherapp", server_nick="other", name="otherapp"))


# ---------------------------------------------------------------------------
# Document (file) move and rename
# ---------------------------------------------------------------------------

def test_mv_document_rename_same_collection(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["mv", "myapp:/docs/old.xml", "myapp:/docs/new.xml"])
    assert result.exit_code == 0
    client_mock.move_document.assert_called_once_with(
        "/db/myapp/docs/old.xml", "/db/myapp/docs/new.xml"
    )


def test_mv_document_move_to_different_collection(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["mv", "myapp:/src/doc.xml", "myapp:/dst/doc.xml"])
    assert result.exit_code == 0
    client_mock.move_document.assert_called_once_with(
        "/db/myapp/src/doc.xml", "/db/myapp/dst/doc.xml"
    )


def test_mv_document_into_collection_trailing_slash(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["mv", "myapp:/doc.xml", "myapp:/archive/"])
    assert result.exit_code == 0
    client_mock.move_document.assert_called_once_with(
        "/db/myapp/doc.xml", "/db/myapp/archive/doc.xml"
    )


def test_mv_document_at_root_path(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["mv", "myapp:/a.xml", "myapp:/b.xml"])
    assert result.exit_code == 0
    client_mock.move_document.assert_called_once_with(
        "/db/myapp/a.xml", "/db/myapp/b.xml"
    )


# ---------------------------------------------------------------------------
# Collection move and rename
# ---------------------------------------------------------------------------

def test_mv_collection_rename(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = []
    result = runner.invoke(app, ["mv", "myapp:/old_col", "myapp:/new_col"])
    assert result.exit_code == 0
    client_mock.create_collection.assert_called_once_with("/db/myapp/new_col")
    client_mock.delete_collection.assert_called_once_with("/db/myapp/old_col")


def test_mv_collection_into_parent(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = []
    result = runner.invoke(app, ["mv", "myapp:/sub", "myapp:/parent/"])
    assert result.exit_code == 0
    client_mock.create_collection.assert_called_once_with("/db/myapp/parent/sub")
    client_mock.delete_collection.assert_called_once_with("/db/myapp/sub")


def test_mv_collection_with_documents_copies_then_deletes(config_with_collection, client_mock, runner):
    from exist_shell.models import DocumentResult, ResourceEntry

    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = [
        ResourceEntry(name="a.xml", mime_type="application/xml"),
        ResourceEntry(name="b.xml", mime_type="application/xml"),
    ]
    client_mock.get_document.return_value = DocumentResult(content=b"<x/>", mime_type="application/xml")

    result = runner.invoke(app, ["mv", "myapp:/src", "myapp:/dst"])
    assert result.exit_code == 0
    assert client_mock.get_document.call_count == 2
    assert client_mock.put_document.call_count == 2
    client_mock.delete_collection.assert_called_once_with("/db/myapp/src")


def test_mv_collection_uploads_before_deleting(config_with_collection, client_mock, runner):
    """put_document must be called before delete_collection."""
    from exist_shell.models import DocumentResult, ResourceEntry

    call_order: list[str] = []
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = [
        ResourceEntry(name="doc.xml", mime_type="application/xml"),
    ]
    client_mock.get_document.return_value = DocumentResult(content=b"<x/>", mime_type="application/xml")
    client_mock.put_document.side_effect = lambda *_: call_order.append("put")
    client_mock.delete_collection.side_effect = lambda *_: call_order.append("delete")

    result = runner.invoke(app, ["mv", "myapp:/src", "myapp:/dst"])
    assert result.exit_code == 0
    assert call_order == ["put", "delete"]


def test_mv_collection_with_subcollections(config_with_collection, client_mock, runner):
    from exist_shell.models import CollectionEntry, DocumentResult, ResourceEntry

    client_mock.is_collection.return_value = True

    def list_side_effect(path: str):
        if path == "/db/myapp/src":
            return [CollectionEntry(name="sub"), ResourceEntry(name="root.xml")]
        if path == "/db/myapp/src/sub":
            return [ResourceEntry(name="child.xml")]
        return []

    client_mock.list_collection.side_effect = list_side_effect
    client_mock.get_document.return_value = DocumentResult(content=b"<x/>", mime_type="application/xml")

    result = runner.invoke(app, ["mv", "myapp:/src", "myapp:/dst"])
    assert result.exit_code == 0
    assert client_mock.put_document.call_count == 2
    # Subcollection must be created at destination
    created_paths = [call.args[0] for call in client_mock.create_collection.call_args_list]
    assert "/db/myapp/dst" in created_paths
    assert "/db/myapp/dst/sub" in created_paths
    client_mock.delete_collection.assert_called_once_with("/db/myapp/src")


def test_mv_empty_collection_creates_and_deletes(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = []

    result = runner.invoke(app, ["mv", "myapp:/empty", "myapp:/newempty"])
    assert result.exit_code == 0
    client_mock.create_collection.assert_called_once_with("/db/myapp/newempty")
    client_mock.put_document.assert_not_called()
    client_mock.delete_collection.assert_called_once_with("/db/myapp/empty")


# ---------------------------------------------------------------------------
# Validation errors
# ---------------------------------------------------------------------------

def test_mv_both_local_fails(runner):
    result = runner.invoke(app, ["mv", "/local/src.xml", "/local/dst.xml"])
    assert result.exit_code == 1
    assert "remote" in result.output


def test_mv_source_local_fails(runner):
    result = runner.invoke(app, ["mv", "/local/src.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1
    assert "remote" in result.output


def test_mv_target_local_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mv", "myapp:/src.xml", "/local/dst.xml"])
    assert result.exit_code == 1
    assert "remote" in result.output


def test_mv_unknown_source_collection_fails(config_path, runner):
    result = runner.invoke(app, ["mv", "ghost:/doc.xml", "ghost:/new.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_mv_cross_server_fails(config_two_servers, runner):
    result = runner.invoke(app, ["mv", "myapp:/doc.xml", "otherapp:/doc.xml"])
    assert result.exit_code == 1
    assert "cross-server" in result.output


def test_mv_source_path_traversal_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mv", "myapp:/../secret.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_mv_target_path_traversal_fails(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["mv", "myapp:/src.xml", "myapp:/../secret.xml"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_mv_collection_onto_itself_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["mv", "myapp:/a", "myapp:/a"])
    assert result.exit_code == 1
    assert "same as, or inside" in result.output
    client_mock.delete_collection.assert_not_called()
    client_mock.create_collection.assert_not_called()
    client_mock.put_document.assert_not_called()


def test_mv_collection_into_itself_trailing_slash_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    result = runner.invoke(app, ["mv", "myapp:/a", "myapp:/a/"])
    assert result.exit_code == 1
    assert "same as, or inside" in result.output
    client_mock.delete_collection.assert_not_called()
    client_mock.create_collection.assert_not_called()
    client_mock.put_document.assert_not_called()


def test_mv_document_onto_itself_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    result = runner.invoke(app, ["mv", "myapp:/doc.xml", "myapp:/doc.xml"])
    assert result.exit_code == 1
    assert "same as, or inside" in result.output
    client_mock.move_document.assert_not_called()


# ---------------------------------------------------------------------------
# Server errors
# ---------------------------------------------------------------------------

def test_mv_document_not_found_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = False
    client_mock.move_document.side_effect = ExistNotFoundError("/db/myapp/missing.xml")
    result = runner.invoke(app, ["mv", "myapp:/missing.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_mv_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["mv", "myapp:/doc.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_mv_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["mv", "myapp:/doc.xml", "myapp:/dst.xml"])
    assert result.exit_code == 1


def test_mv_collection_get_document_error_fails(config_with_collection, client_mock, runner):
    client_mock.is_collection.return_value = True
    client_mock.list_collection.return_value = []
    client_mock.create_collection.side_effect = ExistNotFoundError("/db/myapp/dst")
    result = runner.invoke(app, ["mv", "myapp:/src", "myapp:/dst"])
    assert result.exit_code == 1
    assert "not found" in result.output
