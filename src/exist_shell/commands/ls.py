"""ls command — list contents of an eXist collection path."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.models import CollectionEntry, CollectionItem, ResourceEntry
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def _sort_key_time(item: CollectionItem) -> str:
    """Return the best available timestamp for sorting."""
    if isinstance(item, ResourceEntry):
        return item.last_modified or item.created or ""
    return item.created or ""


def ls(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=collection_target_completer("any"),
    ),
    sort: str = typer.Option("name", "--sort", "-s", help="Sort by: name, time."),
    reverse: bool = typer.Option(False, "--reverse", "-r", help="Reverse sort order."),
    names_only: bool = typer.Option(False, "--names-only", help="Print only names, one per line."),
) -> None:
    """List subcollections and resources at a collection path."""
    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            items = client.list_collection(full_path)

    if sort == "time":
        items = sorted(items, key=_sort_key_time, reverse=reverse)
    else:
        items = sorted(items, key=lambda x: x.name, reverse=reverse)

    if names_only:
        for item in items:
            display_name = f"{item.name}/" if isinstance(item, CollectionEntry) else item.name
            typer.echo(display_name)
        return

    rows: list[tuple[str, str, str, str]] = []
    for item in items:
        display_name = f"{item.name}/" if isinstance(item, CollectionEntry) else item.name
        if isinstance(item, CollectionEntry):
            rows.append((display_name, item.permissions or "", item.owner or "", item.created or ""))
        else:
            assert isinstance(item, ResourceEntry)
            rows.append((
                display_name,
                item.permissions or "",
                item.owner or "",
                item.last_modified or item.created or "",
            ))

    if not rows:
        return

    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        padded = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:-1]))
        typer.echo(f"{padded}  {row[-1]}")
