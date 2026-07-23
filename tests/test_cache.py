import time
from unittest.mock import patch

import pytest

import exist_shell.cache as cache_module
from exist_shell.cache import _get_cache_dir as _real_get_cache_dir
from exist_shell.cache import get_cached, get_cached_groups, get_cached_prefix_match, get_cached_users, invalidate, set_cached, set_cached_groups, set_cached_users
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


def test_different_prefixes_are_cached_separately():
    items_a = [CollectionEntry(name="alpha")]
    items_b = [CollectionEntry(name="beta")]
    set_cached("myapp", "/", items_a, "al")
    set_cached("myapp", "/", items_b, "be")
    assert get_cached("myapp", "/", "al")[0].name == "alpha"  # type: ignore[index]
    assert get_cached("myapp", "/", "be")[0].name == "beta"  # type: ignore[index]
    assert get_cached("myapp", "/") is None


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
# get_cached_prefix_match: ancestor-prefix reuse
# ---------------------------------------------------------------------------


def test_prefix_match_exact_hit():
    items = [ResourceEntry(name="academia.xml")]
    set_cached("myapp", "/", items, "academi")
    result = get_cached_prefix_match("myapp", "/", "academi")
    assert result is not None
    assert result[0].name == "academia.xml"


def test_prefix_match_reuses_shorter_ancestor():
    items = [
        ResourceEntry(name="academia.xml"),
        ResourceEntry(name="academico.xml"),
        ResourceEntry(name="acadar.xml"),
    ]
    set_cached("myapp", "/", items, "acad")
    result = get_cached_prefix_match("myapp", "/", "academi")
    assert result is not None
    assert {i.name for i in result} == {"academia.xml", "academico.xml"}


def test_prefix_match_walks_multiple_ancestors():
    items = [ResourceEntry(name="academia.xml"), ResourceEntry(name="acadar.xml")]
    set_cached("myapp", "/", items, "a")
    result = get_cached_prefix_match("myapp", "/", "academi")
    assert result is not None
    assert [i.name for i in result] == ["academia.xml"]


def test_prefix_match_no_ancestor_cached_misses():
    assert get_cached_prefix_match("myapp", "/", "academi") is None


def test_prefix_match_does_not_reuse_stale_ancestor():
    items = [ResourceEntry(name="academia.xml")]
    set_cached("myapp", "/", items, "acad")
    with patch.object(cache_module, "CACHE_TTL", -1.0):
        assert get_cached_prefix_match("myapp", "/", "academi") is None


def test_prefix_match_empty_prefix_ancestor():
    items = [ResourceEntry(name="a.xml"), ResourceEntry(name="b.xml")]
    set_cached("myapp", "/", items, "")
    result = get_cached_prefix_match("myapp", "/", "a")
    assert result is not None
    assert [i.name for i in result] == ["a.xml"]


def test_prefix_match_skips_truncated_ancestor():
    items = [ResourceEntry(name="academia.xml")]
    set_cached("myapp", "/", items, "acad", truncated=True)
    assert get_cached_prefix_match("myapp", "/", "academi") is None


def test_prefix_match_untruncated_ancestor_still_reused():
    items = [ResourceEntry(name="academia.xml")]
    set_cached("myapp", "/", items, "acad", truncated=False)
    result = get_cached_prefix_match("myapp", "/", "academi")
    assert result is not None
    assert [i.name for i in result] == ["academia.xml"]


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


# ---------------------------------------------------------------------------
# _get_cache_dir real implementation
# ---------------------------------------------------------------------------


def test_get_cache_dir_delegates_to_config(monkeypatch, tmp_path):
    """_real_get_cache_dir bypasses the autouse mock and exercises line 21."""
    from exist_shell.config import Config

    fake_config = Config(cache_dir=tmp_path)
    monkeypatch.setattr(cache_module, "Config", type("_FakeConfig", (), {"load": staticmethod(lambda: fake_config)}))
    result = _real_get_cache_dir()
    assert result == tmp_path / "completions"


# ---------------------------------------------------------------------------
# Silent error paths (except: pass branches)
# ---------------------------------------------------------------------------


def _raise_os_error() -> None:
    raise OSError("simulated disk error")


def test_set_cached_silences_write_error(monkeypatch):
    """set_cached must not propagate exceptions (lines 85-86)."""
    monkeypatch.setattr(cache_module, "_get_cache_dir", _raise_os_error)
    # Should complete without raising
    set_cached("myapp", "/", [CollectionEntry(name="x")])


def test_set_cached_users_silences_write_error(monkeypatch):
    """set_cached_users must not propagate exceptions (lines 135-136)."""
    monkeypatch.setattr(cache_module, "_get_cache_dir", _raise_os_error)
    set_cached_users("local", [UserEntry(username="alice", groups=[])])


def test_set_cached_groups_silences_write_error(monkeypatch):
    """set_cached_groups must not propagate exceptions (lines 172-173)."""
    monkeypatch.setattr(cache_module, "_get_cache_dir", _raise_os_error)
    set_cached_groups("local", [GroupEntry(name="editors", members=[])])


def test_invalidate_silences_glob_error(monkeypatch):
    """invalidate must not propagate exceptions (lines 185-186)."""
    monkeypatch.setattr(cache_module, "_get_cache_dir", _raise_os_error)
    invalidate("myapp")


# ---------------------------------------------------------------------------
# Opportunistic GC of stale cache files
# ---------------------------------------------------------------------------


def test_set_cached_gc_removes_stale_files():
    import os

    set_cached("myapp", "/foo/", [CollectionEntry(name="a")])
    stale_path = next(cache_module._get_cache_dir().glob("myapp@*.json"))
    old_mtime = time.time() - cache_module._GC_MAX_AGE - 1
    os.utime(stale_path, (old_mtime, old_mtime))

    set_cached("myapp", "/bar/", [CollectionEntry(name="b")])

    assert not stale_path.exists()
    assert get_cached("myapp", "/bar/") is not None


def test_set_cached_gc_keeps_fresh_files():
    set_cached("myapp", "/foo/", [CollectionEntry(name="a")])
    set_cached("myapp", "/bar/", [CollectionEntry(name="b")])
    assert get_cached("myapp", "/foo/") is not None
    assert get_cached("myapp", "/bar/") is not None


def test_gc_stale_cache_files_silences_glob_error(monkeypatch):
    monkeypatch.setattr(cache_module, "_get_cache_dir", _raise_os_error)
    cache_module._gc_stale_cache_files()
