from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.main import app
from exist_shell.models import CollectionEntry, ResourceEntry


@pytest.fixture
def client_mock(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.ls.ExistClient", lambda _: mock)
    return mock.__enter__.return_value


@pytest.fixture
def items():
    return [
        CollectionEntry(name="subdir", permissions="rwxr-xr-x", owner="admin"),
        ResourceEntry(name="file.xml", size=1234, mime_type="application/xml"),
    ]


def test_ls_lists_subcollection(config_with_collection, client_mock, items, runner):
    client_mock.list_collection.return_value = items
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 0
    assert "subdir/" in result.output


def test_ls_lists_resource(config_with_collection, client_mock, items, runner):
    client_mock.list_collection.return_value = items
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 0
    assert "file.xml" in result.output


def test_ls_default_path_is_root(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = []
    runner.invoke(app, ["ls", "myapp"])
    client_mock.list_collection.assert_called_once_with("/db/myapp/")


def test_ls_unknown_collection_fails(config_path, client_mock, runner):
    result = runner.invoke(app, ["ls", "ghost:/"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_ls_not_found_path_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistNotFoundError("/db/myapp/missing")
    result = runner.invoke(app, ["ls", "myapp:/missing"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_ls_auth_error_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 1


def test_ls_connection_error_fails(config_with_collection, client_mock, runner):
    client_mock.list_collection.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 1


def test_ls_rejects_path_traversal(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["ls", "myapp:/../other"])
    assert result.exit_code == 1
    assert "traversal" in result.output


def test_ls_columns_separated_by_two_spaces(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = [
        CollectionEntry(name="short", permissions="rwxr-xr-x", owner="admin"),
        ResourceEntry(name="a-much-longer-name.xml", size=42, mime_type="application/xml"),
    ]
    result = runner.invoke(app, ["ls", "myapp:/"])
    assert result.exit_code == 0
    assert "\t" not in result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("a-much-longer-name.xml  42  application/xml")
    assert lines[1].startswith("short/  rwxr-xr-x  admin")


def test_ls_sort_by_name(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = [
        ResourceEntry(name="zebra.xml"),
        ResourceEntry(name="apple.xml"),
        CollectionEntry(name="mango"),
    ]
    result = runner.invoke(app, ["ls", "myapp:/", "--sort", "name"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if l]
    assert lines[0].startswith("apple.xml")
    assert lines[1].startswith("mango/")
    assert lines[2].startswith("zebra.xml")


def test_ls_sort_by_name_reverse(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = [
        ResourceEntry(name="apple.xml"),
        CollectionEntry(name="mango"),
        ResourceEntry(name="zebra.xml"),
    ]
    result = runner.invoke(app, ["ls", "myapp:/", "--sort", "name", "--reverse"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if l]
    assert lines[0].startswith("zebra.xml")
    assert lines[1].startswith("mango/")
    assert lines[2].startswith("apple.xml")


def test_ls_sort_by_time(config_with_collection, client_mock, runner):
    client_mock.list_collection.return_value = [
        ResourceEntry(name="new.xml", last_modified="2024-03-01T00:00:00.000"),
        ResourceEntry(name="old.xml", last_modified="2024-01-01T00:00:00.000"),
        CollectionEntry(name="mid", created="2024-02-01T00:00:00.000"),
    ]
    result = runner.invoke(app, ["ls", "myapp:/", "--sort", "time"])
    assert result.exit_code == 0
    lines = [l for l in result.output.splitlines() if l]
    assert lines[0].startswith("old.xml")
    assert lines[1].startswith("mid/")
    assert lines[2].startswith("new.xml")


def test_ls_names_only(config_with_collection, client_mock, items, runner):
    client_mock.list_collection.return_value = items
    result = runner.invoke(app, ["ls", "myapp:/", "--names-only"])
    assert result.exit_code == 0
    lines = result.output.splitlines()
    assert "subdir/" in lines
    assert "file.xml" in lines
    assert "application/xml" not in result.output
    assert "rwxr-xr-x" not in result.output
