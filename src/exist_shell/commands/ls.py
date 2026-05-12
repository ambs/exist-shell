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

    rows: list[tuple[str, ...]] = []
    for item in items:
        if isinstance(item, CollectionEntry):
            rows.append((
                f"{item.name}/",
                item.permissions or "",
                item.owner or "",
                "",
                "",
                item.created or "",
            ))
        else:
            assert isinstance(item, ResourceEntry)
            rows.append((
                item.name,
                item.permissions or "",
                item.owner or "",
                str(item.size) if item.size is not None else "",
                item.mime_type or "",
                item.last_modified or "",
            ))

    if not rows:
        return

    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        padded = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:-1]))
        typer.echo(f"{padded}  {row[-1]}")
