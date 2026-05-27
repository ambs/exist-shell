import time

import pytest

import exist_shell.cache as cache_module
from exist_shell.cache import get_cached, get_cached_groups, get_cached_users, invalidate, set_cached, set_cached_groups, set_cached_users
from exist_shell.models import CollectionEntry, GroupEntry, ResourceEntry, UserEntry


@pytest.fixture(autouse=True)
def isolated_cache_dir(tmp_path, monkeypatch):
    cache_dir = tmp_path / "completions"
    monkeypatch.setattr(cache_module, "_get_cache_dir", lambda: cache_dir)


def test_get_cached_miss_no_file():
    assert get_cached("myapp", "/") is None


def test_set_and_get_cached_within_ttl():
    items = [CollectionEntry(name="subdir"), ResourceEntry(name="doc.xml")]
    set_cached("myapp", "/", items)
    result = get_cached("myapp", "/")
    assert result is not None
    assert len(result) == 2
    assert isinstance(result[0], CollectionEntry)
    assert result[0].name == "subdir"
    assert isinstance(result[1], ResourceEntry)
    assert result[1].name == "doc.xml"


def test_get_cached_expired(monkeypatch):
    items = [CollectionEntry(name="subdir")]
    set_cached("myapp", "/", items)
    now = time.time()
    monkeypatch.setattr(cache_module.time, "time", lambda: now + cache_module.CACHE_TTL + 1)
    assert get_cached("myapp", "/") is None


def test_different_dir_paths_are_cached_separately():
    items_a = [CollectionEntry(name="a")]
    items_b = [ResourceEntry(name="b.xml")]
    set_cached("myapp", "/foo/", items_a)
    set_cached("myapp", "/bar/", items_b)
    assert get_cached("myapp", "/foo/")[0].name == "a"  # type: ignore[index]
    assert get_cached("myapp", "/bar/")[0].name == "b.xml"  # type: ignore[index]


def test_invalidate_removes_only_target_nick():
    items = [CollectionEntry(name="x")]
    set_cached("alpha", "/", items)
    set_cached("beta", "/", items)
    invalidate("alpha")
    assert get_cached("alpha", "/") is None
    assert get_cached("beta", "/") is not None


def test_invalidate_nonexistent_nick_does_not_raise():
    invalidate("ghost")


def test_set_cached_empty_list():
    set_cached("myapp", "/", [])
    result = get_cached("myapp", "/")
    assert result == []


# ---------------------------------------------------------------------------
# Users cache
# ---------------------------------------------------------------------------


def test_get_cached_users_miss_no_file():
    assert get_cached_users("local") is None


def test_set_and_get_cached_users_within_ttl():
    users = [UserEntry(username="alice", groups=["editors"]), UserEntry(username="admin", groups=["dba"])]
    set_cached_users("local", users)
    result = get_cached_users("local")
    assert result is not None
    assert len(result) == 2
    assert result[0].username == "alice"
    assert result[1].username == "admin"


def test_get_cached_users_expired(monkeypatch):
    set_cached_users("local", [UserEntry(username="alice", groups=[])])
    now = time.time()
    monkeypatch.setattr(cache_module.time, "time", lambda: now + cache_module.SERVER_CACHE_TTL + 1)
    assert get_cached_users("local") is None


def test_cached_users_different_servers_are_independent():
    set_cached_users("local", [UserEntry(username="alice", groups=[])])
    set_cached_users("prod", [UserEntry(username="bob", groups=[])])
    assert get_cached_users("local")[0].username == "alice"  # type: ignore[index]
    assert get_cached_users("prod")[0].username == "bob"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Groups cache
# ---------------------------------------------------------------------------


def test_get_cached_groups_miss_no_file():
    assert get_cached_groups("local") is None


def test_set_and_get_cached_groups_within_ttl():
    groups = [GroupEntry(name="editors", members=["alice"]), GroupEntry(name="dba", members=["admin"])]
    set_cached_groups("local", groups)
    result = get_cached_groups("local")
    assert result is not None
    assert len(result) == 2
    assert result[0].name == "editors"
    assert result[1].name == "dba"


def test_get_cached_groups_expired(monkeypatch):
    set_cached_groups("local", [GroupEntry(name="editors", members=[])])
    now = time.time()
    monkeypatch.setattr(cache_module.time, "time", lambda: now + cache_module.SERVER_CACHE_TTL + 1)
    assert get_cached_groups("local") is None


def test_cached_groups_different_servers_are_independent():
    set_cached_groups("local", [GroupEntry(name="editors", members=[])])
    set_cached_groups("prod", [GroupEntry(name="ops", members=[])])
    assert get_cached_groups("local")[0].name == "editors"  # type: ignore[index]
    assert get_cached_groups("prod")[0].name == "ops"  # type: ignore[index]
