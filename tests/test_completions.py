"""Tests for the shell completion helpers in completions.py."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from exist_shell.completions import collection_target_completer
from exist_shell.config import Collection, Config, Server
from exist_shell.models import CollectionEntry, ResourceEntry


_EXIST_NS = "http://exist.sourceforge.net/NS/exist"


@pytest.fixture
def cfg(config_path):
    """A Config with one server and one collection, saved to the temp path."""
    config = Config.load()
    config.add_server(
        Server(nick="local", host="localhost", port=8080, user="admin", password=SecretStr(""))
    )
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    return Config.load()


@pytest.fixture
def items():
    return [
        CollectionEntry(name="subdir"),
        ResourceEntry(name="doc.xml"),
    ]


# ---------------------------------------------------------------------------
# Config-loading failures
# ---------------------------------------------------------------------------


def test_returns_empty_when_config_load_fails(config_path):
    complete = collection_target_completer()
    with patch("exist_shell.completions.Config.load", side_effect=RuntimeError("boom")):
        assert complete("") == []


# ---------------------------------------------------------------------------
# No colon in incomplete — nick prefix suggestions
# ---------------------------------------------------------------------------


def test_no_colon_allow_local_returns_empty(cfg):
    complete = collection_target_completer(allow_local=True)
    assert complete("myapp") == []


def test_no_colon_returns_matching_nick_suffixed_with_colon(cfg):
    complete = collection_target_completer()
    assert complete("") == ["myapp:"]


def test_no_colon_prefix_filters_nicks(cfg):
    # Add a second collection so we can confirm prefix filtering
    Config.load().add_collection(
        Collection(nick="other", server_nick="local", name="other")
    )
    complete = collection_target_completer()
    results = complete("my")
    assert results == ["myapp:"]
    assert "other:" not in results


def test_no_colon_empty_incomplete_returns_all_nicks(cfg):
    Config.load().add_collection(
        Collection(nick="extra", server_nick="local", name="extra")
    )
    complete = collection_target_completer()
    results = complete("")
    assert "myapp:" in results
    assert "extra:" in results


# ---------------------------------------------------------------------------
# Unknown nick
# ---------------------------------------------------------------------------


def test_unknown_nick_returns_empty(cfg):
    complete = collection_target_completer()
    assert complete("ghost:/") == []


# ---------------------------------------------------------------------------
# Cache hit — no client call
# ---------------------------------------------------------------------------


def test_cache_hit_returns_items_without_calling_client(cfg, items):
    complete = collection_target_completer()
    with (
        patch("exist_shell.completions.get_cached", return_value=items) as mock_get,
        patch("exist_shell.completions.ExistClient") as mock_client,
    ):
        result = complete("myapp:/")
    mock_get.assert_called_once_with("myapp", "/")
    mock_client.assert_not_called()
    assert "myapp:/subdir/" in result
    assert "myapp:/doc.xml" in result


# ---------------------------------------------------------------------------
# Cache miss — calls ExistClient and stores in cache
# ---------------------------------------------------------------------------


def test_cache_miss_calls_client_and_sets_cache(cfg, items):
    complete = collection_target_completer()
    client_instance = MagicMock()
    client_instance.list_collection.return_value = items
    client_context = MagicMock()
    client_context.__enter__ = MagicMock(return_value=client_instance)
    client_context.__exit__ = MagicMock(return_value=False)

    with (
        patch("exist_shell.completions.get_cached", return_value=None),
        patch("exist_shell.completions.ExistClient", return_value=client_context),
        patch("exist_shell.completions.set_cached") as mock_set,
    ):
        result = complete("myapp:/")

    client_instance.list_collection.assert_called_once_with("/db/myapp/")
    mock_set.assert_called_once_with("myapp", "/", items)
    assert "myapp:/subdir/" in result


# ---------------------------------------------------------------------------
# Exception during listing
# ---------------------------------------------------------------------------


def test_listing_exception_returns_empty(cfg):
    complete = collection_target_completer()
    with (
        patch("exist_shell.completions.get_cached", return_value=None),
        patch("exist_shell.completions.ExistClient", side_effect=OSError("conn refused")),
    ):
        assert complete("myapp:/") == []


# ---------------------------------------------------------------------------
# kind filtering
# ---------------------------------------------------------------------------


def test_kind_collection_excludes_resources(cfg, items):
    complete = collection_target_completer(kind="collection")
    with patch("exist_shell.completions.get_cached", return_value=items):
        result = complete("myapp:/")
    assert any("subdir" in r for r in result)
    assert not any("doc.xml" in r for r in result)


def test_kind_resource_excludes_collections(cfg, items):
    complete = collection_target_completer(kind="resource")
    with patch("exist_shell.completions.get_cached", return_value=items):
        result = complete("myapp:/")
    assert any("doc.xml" in r for r in result)
    assert not any("subdir" in r for r in result)


def test_kind_any_includes_both(cfg, items):
    complete = collection_target_completer(kind="any")
    with patch("exist_shell.completions.get_cached", return_value=items):
        result = complete("myapp:/")
    assert any("subdir" in r for r in result)
    assert any("doc.xml" in r for r in result)


# ---------------------------------------------------------------------------
# Prefix filtering
# ---------------------------------------------------------------------------


def test_prefix_filters_results(cfg):
    all_items = [
        CollectionEntry(name="alpha"),
        CollectionEntry(name="beta"),
        ResourceEntry(name="alpha.xml"),
    ]
    complete = collection_target_completer()
    with patch("exist_shell.completions.get_cached", return_value=all_items):
        result = complete("myapp:/al")
    names = [r.split(":", 1)[1] for r in result]
    assert "/alpha/" in names
    assert "/alpha.xml" in names
    assert not any("beta" in n for n in names)


# ---------------------------------------------------------------------------
# Path normalisation — missing leading slash
# ---------------------------------------------------------------------------


def test_partial_path_without_leading_slash_is_normalised(cfg, items):
    """An incomplete like 'myapp:sub' (no leading slash) must still resolve."""
    complete = collection_target_completer()
    client_instance = MagicMock()
    client_instance.list_collection.return_value = items
    client_context = MagicMock()
    client_context.__enter__ = MagicMock(return_value=client_instance)
    client_context.__exit__ = MagicMock(return_value=False)

    with (
        patch("exist_shell.completions.get_cached", return_value=None),
        patch("exist_shell.completions.ExistClient", return_value=client_context),
        patch("exist_shell.completions.set_cached"),
    ):
        result = complete("myapp:sub")

    # dir_path becomes "/" and prefix becomes "sub"; client is called with full_dir
    assert isinstance(result, list)
    called_path = client_instance.list_collection.call_args[0][0]
    assert called_path.startswith("/db/myapp/")


# ---------------------------------------------------------------------------
# Result format: collections trail with "/" and resources do not
# ---------------------------------------------------------------------------


def test_collection_entry_has_trailing_slash(cfg):
    items = [CollectionEntry(name="books")]
    complete = collection_target_completer()
    with patch("exist_shell.completions.get_cached", return_value=items):
        result = complete("myapp:/")
    assert result == ["myapp:/books/"]


def test_resource_entry_has_no_trailing_slash(cfg):
    items = [ResourceEntry(name="readme.xml")]
    complete = collection_target_completer()
    with patch("exist_shell.completions.get_cached", return_value=items):
        result = complete("myapp:/")
    assert result == ["myapp:/readme.xml"]
