"""Shell completion helpers for eXist collection and document paths."""

from typing import Literal

from exist_shell.cache import get_cached, set_cached
from exist_shell.client import ExistClient
from exist_shell.config import Config
from exist_shell.models import CollectionEntry

Kind = Literal["any", "collection", "resource"]


def collection_target_completer(kind: Kind = "any", *, allow_local: bool = False):
    """Return a completion function for ``<nick>:<path>`` arguments filtered by item kind.

    Args:
        kind: Which item types to include — ``"collection"`` for subcollections
            only, ``"resource"`` for documents only, ``"any"`` for both.
        allow_local: When True and the incomplete string contains no ``:``,
            return an empty list so the shell falls back to its default
            filesystem completion.  When False (default), offer collection
            nick completions instead.

    Returns:
        A completion function compatible with Typer's ``autocompletion`` parameter.
    """
    def _complete(incomplete: str) -> list[str]:
        try:
            config = Config.load()
        except Exception:
            return []

        if ":" not in incomplete:
            if allow_local:
                return []
            return [f"{nick}:" for nick in config.collections if nick.startswith(incomplete)]

        nick, partial_path = incomplete.split(":", 1)
        if nick not in config.collections:
            return []

        if not partial_path.startswith("/"):
            partial_path = "/" + partial_path

        last_slash = partial_path.rfind("/")
        dir_path = partial_path[: last_slash + 1]
        prefix = partial_path[last_slash + 1:]

        collection = config.collections[nick]
        server = config.servers[collection.server_nick]
        full_dir = f"/db/{collection.name}{dir_path}"

        try:
            items = get_cached(nick, dir_path)
            if items is None:
                with ExistClient(server) as client:
                    items = client.list_collection(full_dir)
                set_cached(nick, dir_path, items)
        except Exception:
            return []

        results = []
        for item in items:
            is_col = isinstance(item, CollectionEntry)
            if kind == "collection" and not is_col:
                continue
            if kind == "resource" and is_col:
                continue
            item_name = item.name + ("/" if is_col else "")
            if item_name.startswith(prefix):
                results.append(f"{nick}:{dir_path}{item_name}")
        return results

    return _complete


def user_arg_completer(incomplete: str) -> list[str]:
    """Complete ``user@server`` arguments by offering server-profile suffixes.

    Handles three forms:

    - No ``@`` present: returns nothing (usernames are open-ended).
    - ``alice@``: returns ``alice@<nick>`` for each server whose nick starts
      with the text after ``@``.
    - ``alice@prod``: already resolved, returns nothing.

    Args:
        incomplete: The partially typed argument value.

    Returns:
        List of completion candidates.
    """
    try:
        config = Config.load()
    except Exception:
        return []
    if "@" in incomplete:
        user_part, _, server_part = incomplete.rpartition("@")
        return [f"{user_part}@{nick}" for nick in config.servers if nick.startswith(server_part)]
    return []


def server_at_completer(incomplete: str) -> list[str]:
    """Complete a bare ``@server`` argument (used by commands like ``user ls``).

    Args:
        incomplete: The partially typed argument value (e.g. ``@`` or ``@pr``).

    Returns:
        List of ``@nick`` candidates whose nick starts with the text after ``@``.
    """
    try:
        config = Config.load()
    except Exception:
        return []
    if incomplete.startswith("@"):
        prefix = incomplete[1:]
        return [f"@{nick}" for nick in config.servers if nick.startswith(prefix)]
    if not incomplete:
        return [f"@{nick}" for nick in config.servers]
    return []
