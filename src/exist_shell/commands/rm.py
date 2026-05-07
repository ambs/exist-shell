"""rm command — delete documents from an eXist collection path."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def rm(
    targets: list[str] = typer.Argument(
        help="One or more collection and document paths: <nick>:<path>.",
        autocompletion=collection_target_completer("resource"),
    ),
) -> None:
    """Delete one or more documents from a collection path."""
    for target in targets:
        nick, path = parse_target(target)
        collection, server, full_path = resolve_collection(nick, path)

        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                client.delete_document(full_path)
