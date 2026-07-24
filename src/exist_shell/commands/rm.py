"""rm command — delete documents or collections from an eXist collection path."""

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def rm(
    targets: list[str] = typer.Argument(
        help="One or more collection and document paths: <nick>:<path>.",
        autocompletion=collection_target_completer("resource"),
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-r", help="Allow deleting a collection and everything under it."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt when deleting a collection."),
) -> None:
    """Delete one or more documents from a collection path.

    A target that is itself a collection is refused unless ``--recursive`` is
    given, since deleting it removes the entire subtree with no undo.
    """
    for target in targets:
        nick, path = parse_target(target)
        collection, server, full_path = resolve_collection(nick, path)

        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                if client.is_collection(full_path):
                    if not recursive:
                        typer.echo(
                            f"Error: '{nick}:{path}' is a collection; "
                            "use -r/--recursive to delete it and everything under it.",
                            err=True,
                        )
                        raise typer.Exit(1)
                    if not yes:
                        typer.confirm(
                            f"Delete collection '{nick}:{path}' and everything under it?", abort=True
                        )
                    client.delete_collection(full_path)
                else:
                    client.delete_document(full_path)
                invalidate(nick)
