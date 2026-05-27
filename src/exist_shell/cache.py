"""File-based TTL cache for shell completion listings."""

import hashlib
import json
import time
from pathlib import Path

from exist_shell.config import Config
from exist_shell.models import CollectionEntry, CollectionItem, GroupEntry, ResourceEntry, UserEntry

CACHE_TTL = 5.0
SERVER_CACHE_TTL = 60.0


def _get_cache_dir() -> Path:
    """Return the completions cache directory, resolved from the active config.

    Returns:
        Path to the completions cache directory.
    """
    return Config.load().resolved_cache_dir() / "completions"


def _cache_path(nick: str, dir_path: str) -> Path:
    """Return the cache file path for a (nick, dir_path) pair.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection (e.g. ``/books/``).

    Returns:
        Path to the cache file.
    """
    digest = hashlib.sha256(dir_path.encode()).hexdigest()[:16]
    return _get_cache_dir() / f"{nick}@{digest}.json"


def get_cached(nick: str, dir_path: str) -> list[CollectionItem] | None:
    """Return a cached directory listing if it exists and is still fresh.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.

    Returns:
        List of ``CollectionItem`` objects, or ``None`` on cache miss or expiry.
    """
    path = _cache_path(nick, dir_path)
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
        return items
    except Exception:
        return None


def set_cached(nick: str, dir_path: str, items: list[CollectionItem]) -> None:
    """Write a directory listing to the cache atomically.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection.
        items: List of ``CollectionItem`` objects to cache.
    """
    try:
        _get_cache_dir().mkdir(parents=True, exist_ok=True)
        serialized = []
        for item in items:
            d = item.model_dump()
            d["kind"] = "collection" if isinstance(item, CollectionEntry) else "resource"
            serialized.append(d)
        payload = json.dumps({"ts": time.time(), "items": serialized})
        cache_path = _cache_path(nick, dir_path)
        tmp = cache_path.with_suffix(".tmp")
        tmp.write_text(payload)
        tmp.rename(cache_path)
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
