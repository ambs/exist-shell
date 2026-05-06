"""File-based TTL cache for shell completion listings."""

import hashlib
import json
import time
from pathlib import Path

from exist_shell.models import CollectionEntry, CollectionItem, ResourceEntry

CACHE_DIR = Path.home() / ".cache" / "exsh" / "completions"
CACHE_TTL = 5.0


def _cache_path(nick: str, dir_path: str) -> Path:
    """Return the cache file path for a (nick, dir_path) pair.

    Args:
        nick: Collection nick name.
        dir_path: Directory path within the collection (e.g. ``/books/``).

    Returns:
        Path to the cache file.
    """
    digest = hashlib.sha256(dir_path.encode()).hexdigest()[:16]
    return CACHE_DIR / f"{nick}@{digest}.json"


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
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
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


def invalidate(nick: str) -> None:
    """Delete all cached listings for the given nick.

    Args:
        nick: Collection nick name whose cache entries should be removed.
    """
    try:
        for f in CACHE_DIR.glob(f"{nick}@*.json"):
            f.unlink(missing_ok=True)
    except Exception:
        pass
