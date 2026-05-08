"""Collection management commands (add, ls, rm)."""

import typer

from exist_shell.client import ExistClient
from exist_shell.config import Collection, Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError

app = typer.Typer(help="Manage collections.", no_args_is_help=True)


def _complete_collection_target(incomplete: str) -> list[str]:
    if "@" not in incomplete:
        return []
    prefix, partial = incomplete.split("@", 1)
    try:
        servers = Config.load().servers
    except Exception:
        return []
    return [f"{prefix}@{nick}" for nick in servers if nick.startswith(partial)]


def _list() -> None:
    config = Config.load()
    for nick, c in config.collections.items():
        typer.echo(f"{nick}\t/db/{c.name}\t@{c.server_nick}")


app.command("ls", help="List configured collections.")(_list)
app.command("list", help="List configured collections.", hidden=True)(_list)


@app.command("add")
def collection_add(
    target: str = typer.Argument(
        help="Collection name, optionally with server: <name>[@<server>].",
        autocompletion=_complete_collection_target,
    ),
    server: str | None = typer.Option(None, "--server", help="Server nick."),
    nick: str | None = typer.Option(None, help="Nickname (default: collection name)."),
) -> None:
    """Add a collection and verify it exists on the server before saving."""
    name = target
    if "@" in target:
        name, server_from_target = target.split("@", 1)
        if server is not None and server != server_from_target:
            typer.echo("Error: conflicting --server and @server in argument.", err=True)
            raise typer.Exit(1)
        server = server_from_target

    config = Config.load()

    if server is None:
        if len(config.servers) == 1:
            server = next(iter(config.servers))
        else:
            typer.echo("Error: --server is required when multiple servers are configured.", err=True)
            raise typer.Exit(1)

    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)

    resolved_nick = nick or name
    if resolved_nick in config.collections:
        typer.echo(
            f"Error: nick '{resolved_nick}' already exists. Use --nick to provide a unique nickname.",
            err=True,
        )
        raise typer.Exit(1)

    try:
        with ExistClient(config.servers[server]) as client:
            if not client.collection_exists(name):
                typer.echo(f"Error: '/db/{name}' not found on server '{server}'.", err=True)
                raise typer.Exit(1)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    config.add_collection(Collection(nick=resolved_nick, server_nick=server, name=name))
    typer.echo(f"Collection '{resolved_nick}' added.")


@app.command("rm")
def collection_rm(
    nick: str = typer.Argument(help="Nickname of the collection to remove."),
    delete: bool = typer.Option(False, "--delete", help="Also delete the collection from the server."),
) -> None:
    """Remove a collection from the config, optionally deleting it from the server."""
    config = Config.load()
    if nick not in config.collections:
        typer.echo(f"Error: collection '{nick}' not found.", err=True)
        raise typer.Exit(1)

    if delete:
        collection = config.collections[nick]
        if collection.server_nick not in config.servers:
            typer.echo(f"Error: server '{collection.server_nick}' not found.", err=True)
            raise typer.Exit(1)
        try:
            with ExistClient(config.servers[collection.server_nick]) as client:
                client.delete_collection(f"/db/{collection.name}")
        except ExistAuthError:
            typer.echo(f"Error: authentication failed for server '{collection.server_nick}'.", err=True)
            raise typer.Exit(1)
        except ExistConnectionError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
        except ExistNotFoundError:
            typer.echo(
                f"Error: '/db/{collection.name}' not found on server '{collection.server_nick}'.",
                err=True,
            )
            raise typer.Exit(1)

    config.remove_collection(nick)
    typer.echo(f"Collection '{nick}' removed.")
