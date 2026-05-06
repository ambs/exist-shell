"""ls command — list contents of an eXist collection path."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.models import CollectionEntry, ResourceEntry
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def ls(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=collection_target_completer("any"),
    ),
) -> None:
    """List subcollections and resources at a collection path."""
    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            items = client.list_collection(full_path)

    for item in items:
        if isinstance(item, CollectionEntry):
            typer.echo(f"{item.name}/\t{item.permissions or ''}\t{item.owner or ''}\t{item.created or ''}")
        else:
            assert isinstance(item, ResourceEntry)
            typer.echo(f"{item.name}\t{item.permissions or ''}\t{item.owner or ''}\t{item.size or ''}\t{item.mime_type or ''}\t{item.last_modified or ''}")
