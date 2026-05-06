import typer

from exist_shell.client import ExistClient
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.models import CollectionEntry, ResourceEntry


def _complete_ls_target(incomplete: str) -> list[str]:
    try:
        config = Config.load()
    except Exception:
        return []

    if ":" not in incomplete:
        return [f"{nick}:" for nick in config.collections if nick.startswith(incomplete)]

    nick, partial_path = incomplete.split(":", 1)
    if nick not in config.collections:
        return []

    if not partial_path.startswith("/"):
        partial_path = "/" + partial_path

    last_slash = partial_path.rfind("/")
    dir_path = partial_path[: last_slash + 1]
    prefix = partial_path[last_slash + 1 :]

    collection = config.collections[nick]
    server = config.servers[collection.server_nick]
    full_dir = f"/db/{collection.name}{dir_path}"

    try:
        with ExistClient(server) as client:
            items = client.list_collection(full_dir)
    except Exception:
        return []

    results = []
    for item in items:
        item_name = item.name + ("/" if isinstance(item, CollectionEntry) else "")
        if item_name.startswith(prefix):
            results.append(f"{nick}:{dir_path}{item_name}")
    return results


def ls(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=_complete_ls_target,
    ),
) -> None:
    nick, _, path = target.partition(":")
    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path

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
