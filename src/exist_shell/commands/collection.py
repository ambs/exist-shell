import typer

from exist_shell.client import ExistClient
from exist_shell.config import Collection, Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError

app = typer.Typer(help="Manage collections.", no_args_is_help=True)


def _list() -> None:
    config = Config.load()
    for nick, c in config.collections.items():
        typer.echo(f"{nick}\t/db/{c.name}\t@{c.server_nick}")


app.command("ls", help="List configured collections.")(_list)
app.command("list", help="List configured collections.", hidden=True)(_list)


@app.command("add")
def collection_add(
    name: str = typer.Argument(help="Collection name under /db/."),
    server: str | None = typer.Option(None, "--server", help="Server nick."),
    nick: str | None = typer.Option(None, help="Nickname (default: collection name)."),
) -> None:
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
