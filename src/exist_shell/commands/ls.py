"""ls command — list contents of an eXist collection path."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.models import CollectionEntry, ResourceEntry
from exist_shell.utils import validate_path


def ls(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=collection_target_completer("any"),
    ),
) -> None:
    """List subcollections and resources at a collection path."""
    nick, _, path = target.partition(":")
    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path

    try:
        validate_path(path)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    config = Config.load()
    if nick not in config.collections:
        typer.echo(f"Error: collection '{nick}' not found.", err=True)
        raise typer.Exit(1)

    collection = config.collections[nick]
    server = config.servers[collection.server_nick]
    full_path = f"/db/{collection.name}{path}"

    try:
        with ExistClient(server) as client:
            items = client.list_collection(full_path)
    except ExistNotFoundError:
        typer.echo(f"Error: path '{path}' not found in collection '{nick}'.", err=True)
        raise typer.Exit(1)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{collection.server_nick}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    for item in items:
        if isinstance(item, CollectionEntry):
            typer.echo(f"{item.name}/\t{item.permissions or ''}\t{item.owner or ''}\t{item.created or ''}")
        else:
            assert isinstance(item, ResourceEntry)
            typer.echo(f"{item.name}\t{item.permissions or ''}\t{item.owner or ''}\t{item.size or ''}\t{item.mime_type or ''}\t{item.last_modified or ''}")
