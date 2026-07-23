"""File-based TTL cache for shell completion listings."""

import hashlib
import json
import time
from pathlib import Path

from exist_shell.config import Config
from exist_shell.models import CollectionEntry, CollectionItem, GroupEntry, ResourceEntry, UserEntry

CACHE_TTL = 30.0
SERVER_CACHE_TTL = 60.0
_GC_MAX_AGE = 3600.0


def _get_cache_dir() -> Path:
    """Return the completions cache directory, resolved from the active config.

    Returns:
        Path to the completions cache directory.
    """
    return Config.load().resolved_cache_dir() / "completions"


def _cache_path(nick: str, dir_path: str, prefix: str = "") -> Path:
    """Return the cache file path for a (nick, dir_path, prefix) triple.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection (e.g. ``/books/``).
        prefix: Name prefix the listing was filtered by, if any.

    Returns:
        Path to the cache file.
    """
    digest = hashlib.sha256(f"{dir_path}\x00{prefix}".encode()).hexdigest()[:16]
    return _get_cache_dir() / f"{nick}@{digest}.json"


def _read_entry(nick: str, dir_path: str, prefix: str = "") -> tuple[list[CollectionItem], bool] | None:
    """Return a cache entry's items and truncation flag if it exists and is still fresh.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.
        prefix: Name prefix the listing was filtered by, if any.

    Returns:
        A ``(items, truncated)`` tuple, or ``None`` on cache miss or expiry.
    """
    path = _cache_path(nick, dir_path, prefix)
    try:
        data = json.loads(path.read_text())
        if time.time() - data["ts"] > CACHE_TTL:
            return None
        items: list[CollectionItem] = []
        for raw in data["items"]:
            kind = raw.pop("kind")
            if kind == "collection":
                items.append(CollectionEntry.model_validate(raw))
            else:
                items.append(ResourceEntry.model_validate(raw))
        return items, bool(data.get("truncated", False))
    except Exception:
        return None


def get_cached(nick: str, dir_path: str, prefix: str = "") -> list[CollectionItem] | None:
    """Return a cached directory listing if it exists and is still fresh.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.
        prefix: Name prefix the listing was filtered by, if any.

    Returns:
        List of ``CollectionItem`` objects, or ``None`` on cache miss or expiry.
    """
    entry = _read_entry(nick, dir_path, prefix)
    return entry[0] if entry is not None else None


def get_cached_prefix_match(nick: str, dir_path: str, prefix: str) -> list[CollectionItem] | None:
    """Return a listing for ``prefix``, reusing a cached broader-prefix entry when possible.

    Tries an exact cache hit first. On a miss, walks ``prefix`` down to
    shorter ancestor prefixes (e.g. "academi" -> "academ" -> ... -> "acad")
    looking for a fresh cache entry — since any listing cached under a
    shorter prefix is a superset of what a longer, more specific prefix
    would return, it can be filtered client-side instead of re-querying the
    server. This lets progressive tab-completion (typing more characters
    between presses) stay served from a single cached fetch.

    An ancestor entry that was itself truncated (its listing hit the
    server-side cap) is not a true superset — its items are just whichever
    ones sorted first, not necessarily every one that matches ``prefix`` — so
    it's skipped rather than filtered client-side. Since any broader
    (shorter) ancestor can only have at least as many matches, it would
    have hit the same cap too, so the walk stops there instead of trying
    shorter prefixes.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.
        prefix: Name prefix to filter by.

    Returns:
        List of ``CollectionItem`` objects matching ``prefix``, or ``None`` if
        neither an exact nor a usable ancestor-prefix cache entry is fresh.
    """
    entry = _read_entry(nick, dir_path, prefix)
    if entry is not None:
        return entry[0]
    for cut in range(len(prefix) - 1, -1, -1):
        ancestor = _read_entry(nick, dir_path, prefix[:cut])
        if ancestor is None:
            continue
        ancestor_items, ancestor_truncated = ancestor
        if ancestor_truncated:
            return None
        return [item for item in ancestor_items if item.name.startswith(prefix)]
    return None


def _gc_stale_cache_files() -> None:
    """Opportunistically remove cache files older than `_GC_MAX_AGE`.

    Called on every `set_cached` so the distinct (dir_path, prefix) files
    created while typing accumulate for at most an hour instead of
    indefinitely; the only other thing that prunes them is an explicit
    `invalidate(nick)`.
    """
    try:
        cutoff = time.time() - _GC_MAX_AGE
        for f in _get_cache_dir().glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
    except Exception:
        pass


def set_cached(
    nick: str, dir_path: str, items: list[CollectionItem], prefix: str = "", truncated: bool = False
) -> None:
    """Write a directory listing to the cache atomically.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.
        items: List of ``CollectionItem`` objects to cache.
        prefix: Name prefix the listing was filtered by, if any.
        truncated: Whether `items` was capped by a server-side listing
            limit, and so isn't a complete superset for ancestor-prefix reuse.
    """
    try:
        _get_cache_dir().mkdir(parents=True, exist_ok=True)
        serialized = []
        for item in items:
            d = item.model_dump()
            d["kind"] = "collection" if isinstance(item, CollectionEntry) else "resource"
            serialized.append(d)
        payload = json.dumps({"ts": time.time(), "items": serialized, "truncated": truncated})
        cache_path = _cache_path(nick, dir_path, prefix)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.rename(cache_path)
        _gc_stale_cache_files()
    except Exception:
        pass


def _server_cache_path(server_nick: str, kind: str) -> Path:
    """Return the cache file path for a (server_nick, kind) pair.

    Args:
        server_nick: Server nick name.
        kind: Data kind — ``"users"`` or ``"groups"``.

    Returns:
        Path to the cache file.
    """
    return _get_cache_dir() / f"{server_nick}@{kind}.json"


def get_cached_users(server_nick: str) -> list[UserEntry] | None:
    """Return a cached user list if it exists and is still fresh.

    Args:
        server_nick: Server nick name.

    Returns:
        List of ``UserEntry`` objects, or ``None`` on cache miss or expiry.
    """
    path = _server_cache_path(server_nick, "users")
    try:
        data = json.loads(path.read_text())
        if time.time() - data["ts"] > SERVER_CACHE_TTL:
            return None
        return [UserEntry.model_validate(u) for u in data["items"]]
    except Exception:
        return None


def set_cached_users(server_nick: str, users: list[UserEntry]) -> None:
    """Write a user list to the cache atomically.

    Args:
        server_nick: Server nick name.
        users: List of ``UserEntry`` objects to cache.
    """
    try:
        _get_cache_dir().mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"ts": time.time(), "items": [u.model_dump() for u in users]})
        cache_path = _server_cache_path(server_nick, "users")
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.rename(cache_path)
    except Exception:
        pass


def get_cached_groups(server_nick: str) -> list[GroupEntry] | None:
    """Return a cached group list if it exists and is still fresh.

    Args:
        server_nick: Server nick name.

    Returns:
        List of ``GroupEntry`` objects, or ``None`` on cache miss or expiry.
    """
    path = _server_cache_path(server_nick, "groups")
    try:
        data = json.loads(path.read_text())
        if time.time() - data["ts"] > SERVER_CACHE_TTL:
            return None
        return [GroupEntry.model_validate(g) for g in data["items"]]
    except Exception:
        return None


def set_cached_groups(server_nick: str, groups: list[GroupEntry]) -> None:
    """Write a group list to the cache atomically.

    Args:
        server_nick: Server nick name.
        groups: List of ``GroupEntry`` objects to cache.
    """
    try:
        _get_cache_dir().mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"ts": time.time(), "items": [g.model_dump() for g in groups]})
        cache_path = _server_cache_path(server_nick, "groups")
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.rename(cache_path)
    except Exception:
        pass


def invalidate(nick: str) -> None:
    """Delete all cached listings for the given nick.

    Args:
        nick: Collection nick name whose cache entries should be removed.
    """
    try:
        for f in _get_cache_dir().glob(f"{nick}@*.json"):
            f.unlink(missing_ok=True)
    except Exception:
        pass
