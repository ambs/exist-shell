"""mkdir command — create a collection in eXist-db."""

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def mkdir(
    target: str = typer.Argument(
        help="Collection and new path: <nick>:<path>.",
        autocompletion=collection_target_completer("collection"),
    ),
) -> None:
    """Create a collection at a path inside a registered collection."""
    nick, path = parse_target(target)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            client.create_collection(full_path)
    invalidate(nick)
