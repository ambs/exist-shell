"""Tests for the shell completion helpers in completions.py."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

import exist_shell.completions as completions_module
from exist_shell.completions import chown_spec_completer, collection_target_completer, server_at_completer, server_nick_completer, user_arg_completer
from exist_shell.config import Collection, Config, Server
from exist_shell.models import CollectionEntry, GroupEntry, ResourceEntry, UserEntry


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
    with patch.object(completions_module.Config, "load", side_effect=RuntimeError("boom")):
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
        patch.object(completions_module, "get_cached", return_value=items) as mock_get,
        patch.object(completions_module, "ExistClient") as mock_client,
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
    client_instance.list_child_names.return_value = items
    client_context = MagicMock()
    client_context.__enter__ = MagicMock(return_value=client_instance)
    client_context.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(completions_module, "get_cached", return_value=None),
        patch.object(completions_module, "ExistClient", return_value=client_context) as mock_client,
        patch.object(completions_module, "set_cached") as mock_set,
    ):
        result = complete("myapp:/")

    client_instance.list_child_names.assert_called_once_with("/db/myapp/")
    mock_set.assert_called_once_with("myapp", "/", items)
    assert "myapp:/subdir/" in result
    _, kwargs = mock_client.call_args
    assert kwargs == {"connect_timeout": 2.0, "read_timeout": 4.0}


# ---------------------------------------------------------------------------
# Exception during listing
# ---------------------------------------------------------------------------


def test_listing_exception_returns_empty(cfg):
    complete = collection_target_completer()
    with (
        patch.object(completions_module, "get_cached", return_value=None),
        patch.object(completions_module, "ExistClient", side_effect=OSError("conn refused")),
    ):
        assert complete("myapp:/") == []


# ---------------------------------------------------------------------------
# kind filtering
# ---------------------------------------------------------------------------


def test_kind_collection_excludes_resources(cfg, items):
    complete = collection_target_completer(kind="collection")
    with patch.object(completions_module, "get_cached", return_value=items):
        result = complete("myapp:/")
    assert any("subdir" in r for r in result)
    assert not any("doc.xml" in r for r in result)


def test_kind_resource_excludes_collections(cfg, items):
    complete = collection_target_completer(kind="resource")
    with patch.object(completions_module, "get_cached", return_value=items):
        result = complete("myapp:/")
    assert any("doc.xml" in r for r in result)
    assert not any("subdir" in r for r in result)


def test_kind_any_includes_both(cfg, items):
    complete = collection_target_completer(kind="any")
    with patch.object(completions_module, "get_cached", return_value=items):
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
    with patch.object(completions_module, "get_cached", return_value=all_items):
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
    client_instance.list_child_names.return_value = items
    client_context = MagicMock()
    client_context.__enter__ = MagicMock(return_value=client_instance)
    client_context.__exit__ = MagicMock(return_value=False)

    with (
        patch.object(completions_module, "get_cached", return_value=None),
        patch.object(completions_module, "ExistClient", return_value=client_context),
        patch.object(completions_module, "set_cached"),
    ):
        result = complete("myapp:sub")

    # dir_path becomes "/" and prefix becomes "sub"; client is called with full_dir
    assert isinstance(result, list)
    called_path = client_instance.list_child_names.call_args[0][0]
    assert called_path.startswith("/db/myapp/")


# ---------------------------------------------------------------------------
# Result format: collections trail with "/" and resources do not
# ---------------------------------------------------------------------------


def test_collection_entry_has_trailing_slash(cfg):
    items = [CollectionEntry(name="books")]
    complete = collection_target_completer()
    with patch.object(completions_module, "get_cached", return_value=items):
        result = complete("myapp:/")
    assert result == ["myapp:/books/"]


def test_resource_entry_has_no_trailing_slash(cfg):
    items = [ResourceEntry(name="readme.xml")]
    complete = collection_target_completer()
    with patch.object(completions_module, "get_cached", return_value=items):
        result = complete("myapp:/")
    assert result == ["myapp:/readme.xml"]


# ---------------------------------------------------------------------------
# user_arg_completer
# ---------------------------------------------------------------------------


def test_user_arg_completer_no_at_returns_empty(cfg):
    assert user_arg_completer("alice") == []


def test_user_arg_completer_at_returns_all_servers(cfg):
    results = user_arg_completer("alice@")
    assert "alice@local" in results


def test_user_arg_completer_at_filters_by_prefix(cfg):
    Config.load().add_server(
        Server(nick="prod", host="prod.example.com", password=SecretStr(""))
    )
    results = user_arg_completer("alice@lo")
    assert "alice@local" in results
    assert "alice@prod" not in results


def test_user_arg_completer_exact_match_returns_candidate(cfg):
    results = user_arg_completer("alice@local")
    assert results == ["alice@local"]


def test_user_arg_completer_config_error_returns_empty():
    with patch.object(completions_module.Config, "load", side_effect=RuntimeError("boom")):
        assert user_arg_completer("alice@") == []


# ---------------------------------------------------------------------------
# server_at_completer
# ---------------------------------------------------------------------------


def test_server_at_completer_empty_returns_all(cfg):
    results = server_at_completer("")
    assert "@local" in results


def test_server_at_completer_at_only_returns_all(cfg):
    results = server_at_completer("@")
    assert "@local" in results


def test_server_at_completer_partial_filters(cfg):
    Config.load().add_server(
        Server(nick="prod", host="prod.example.com", password=SecretStr(""))
    )
    results = server_at_completer("@lo")
    assert "@local" in results
    assert "@prod" not in results


def test_server_at_completer_no_at_prefix_returns_empty(cfg):
    assert server_at_completer("local") == []


def test_server_at_completer_config_error_returns_empty():
    with patch.object(completions_module.Config, "load", side_effect=RuntimeError("boom")):
        assert server_at_completer("@") == []


# ---------------------------------------------------------------------------
# server_nick_completer
# ---------------------------------------------------------------------------


def test_server_nick_completer_empty_returns_all(cfg):
    assert server_nick_completer("") == ["local"]


def test_server_nick_completer_matching_prefix(cfg):
    assert server_nick_completer("lo") == ["local"]


def test_server_nick_completer_non_matching_prefix(cfg):
    assert server_nick_completer("xyz") == []


def test_server_nick_completer_config_error_returns_empty():
    with patch.object(completions_module.Config, "load", side_effect=RuntimeError("boom")):
        assert server_nick_completer("") == []


# ---------------------------------------------------------------------------
# chown_spec_completer
# ---------------------------------------------------------------------------


@pytest.fixture
def _client_mock():
    users = [UserEntry(username="alice", groups=[]), UserEntry(username="admin", groups=[])]
    groups = [GroupEntry(name="editors", members=[]), GroupEntry(name="dba", members=[])]
    client = MagicMock()
    client.list_users.return_value = users
    client.list_groups.return_value = groups
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=client)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx, client


def test_chown_spec_completer_config_error_returns_empty():
    with patch.object(completions_module.Config, "load", side_effect=RuntimeError("boom")):
        assert chown_spec_completer("") == []


def test_chown_spec_completer_no_servers_returns_empty(config_path):
    assert chown_spec_completer("") == []


def test_chown_spec_completer_completes_users(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_users", return_value=None), \
         patch.object(completions_module, "set_cached_users"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("")
    assert "alice" in result
    assert "admin" in result


def test_chown_spec_completer_users_cache_hit(cfg, _client_mock):
    ctx, client = _client_mock
    cached = [UserEntry(username="alice", groups=[]), UserEntry(username="admin", groups=[])]
    with patch.object(completions_module, "get_cached_users", return_value=cached), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("")
    client.list_users.assert_not_called()
    assert "alice" in result


def test_chown_spec_completer_filters_users_by_prefix(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_users", return_value=None), \
         patch.object(completions_module, "set_cached_users"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("al")
    assert "alice" in result
    assert "admin" not in result


def test_chown_spec_completer_colon_completes_groups(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_groups", return_value=None), \
         patch.object(completions_module, "set_cached_groups"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("alice:")
    assert "alice:editors" in result
    assert "alice:dba" in result


def test_chown_spec_completer_groups_cache_hit(cfg, _client_mock):
    ctx, client = _client_mock
    cached = [GroupEntry(name="editors", members=[]), GroupEntry(name="dba", members=[])]
    with patch.object(completions_module, "get_cached_groups", return_value=cached), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("alice:")
    client.list_groups.assert_not_called()
    assert "alice:editors" in result


def test_chown_spec_completer_colon_filters_groups_by_prefix(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_groups", return_value=None), \
         patch.object(completions_module, "set_cached_groups"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("alice:ed")
    assert "alice:editors" in result
    assert "alice:dba" not in result


def test_chown_spec_completer_server_prefix_resolves_server(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_users", return_value=None), \
         patch.object(completions_module, "set_cached_users"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("local@")
    assert "local@alice" in result
    assert "local@admin" in result


def test_chown_spec_completer_server_prefix_with_colon_completes_groups(cfg, _client_mock):
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_groups", return_value=None), \
         patch.object(completions_module, "set_cached_groups"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("local@alice:")
    assert "local@alice:editors" in result


def test_chown_spec_completer_unknown_server_prefix_offers_server_nicks(cfg):
    result = chown_spec_completer("lo@")
    assert "local@" in result


def test_chown_spec_completer_multiple_servers_offers_server_nicks(cfg, _client_mock):
    Config.load().add_server(
        Server(nick="prod", host="prod.example.com", password=SecretStr(""))
    )
    ctx, _ = _client_mock
    with patch.object(completions_module, "get_cached_users", return_value=None), \
         patch.object(completions_module, "set_cached_users"), \
         patch.object(completions_module, "ExistClient", return_value=ctx):
        result = chown_spec_completer("")
    assert "local@" in result
    assert "prod@" in result


def test_chown_spec_completer_client_exception_returns_empty(cfg):
    with patch.object(completions_module, "get_cached_users", return_value=None), \
         patch.object(completions_module, "ExistClient", side_effect=OSError("refused")):
        assert chown_spec_completer("") == []
