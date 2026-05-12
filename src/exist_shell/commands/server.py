"""Server management commands (add, ls, rm, rename)."""

import re

import typer

from pydantic import SecretStr

from exist_shell.client import ExistClient
from exist_shell.config import NICK_PATTERN, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError

app = typer.Typer(help="Manage servers.", no_args_is_help=True)


def _default_nick(host: str) -> str:
    return host.split(".")[0]


def _complete_server_nick(incomplete: str) -> list[str]:
    try:
        servers = Config.load().servers
    except Exception:
        return []
    return [nick for nick in servers if nick.startswith(incomplete)]


def _list() -> None:
    config = Config.load()
    for nick, s in config.servers.items():
        typer.echo(f"{nick}\t{s.user}@{s.host}:{s.port}")


app.command("ls", help="List configured servers.")(_list)
app.command("list", help="List configured servers.", hidden=True)(_list)


@app.command("add")
def server_add(
    host: str = typer.Argument(help="Hostname or IP of the eXist server."),
    port: int = typer.Option(8080, help="HTTP port."),
    user: str = typer.Option("admin", help="Username."),
    password: str = typer.Option(
        "",
        "--password",
        envvar="EXIST_PASSWORD",
        hide_input=True,
        prompt="Password (leave empty for none)",
        help="Password.",
    ),
    nick: str | None = typer.Option(None, help="Nickname (default: hostname without domain)."),
) -> None:
    """Add a server and verify connectivity before saving."""
    resolved_nick = nick or _default_nick(host)
    config = Config.load()
    if resolved_nick in config.servers:
        typer.echo(f"Error: server nick '{resolved_nick}' already exists.", err=True)
        raise typer.Exit(1)
    server = Server(nick=resolved_nick, host=host, port=port, user=user, password=SecretStr(password))
    try:
        with ExistClient(server) as client:
            client.check_connection()
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for {host}:{port}.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    config.add_server(server)
    typer.echo(f"Server '{resolved_nick}' added.")


@app.command("rename")
def server_rename(
    old_nick: str = typer.Argument(
        help="Current nickname of the server.", autocompletion=_complete_server_nick
    ),
    new_nick: str = typer.Argument(help="New nickname for the server."),
) -> None:
    """Rename a server nick, updating all collection references."""
    if old_nick == new_nick:
        typer.echo("Error: new nick is the same as the old nick.", err=True)
        raise typer.Exit(1)
    if not re.match(NICK_PATTERN, new_nick):
        typer.echo(f"Error: '{new_nick}' is not a valid server nick.", err=True)
        raise typer.Exit(1)
    config = Config.load()
    if old_nick not in config.servers:
        typer.echo(f"Error: server nick '{old_nick}' not found.", err=True)
        raise typer.Exit(1)
    if new_nick in config.servers:
        typer.echo(f"Error: server nick '{new_nick}' already exists.", err=True)
        raise typer.Exit(1)
    updated = config.rename_server(old_nick, new_nick)
    if updated:
        noun = "collection" if len(updated) == 1 else "collections"
        typer.echo(f"Also updated {len(updated)} {noun}: {', '.join(updated)}.")
    typer.echo(f"Server '{old_nick}' renamed to '{new_nick}'.")


@app.command("rm")
def server_rm(
    nick: str = typer.Argument(help="Nickname of the server to remove."),
) -> None:
    """Remove a server and all its registered collections from the config."""
    config = Config.load()
    if nick not in config.servers:
        typer.echo(f"Error: server nick '{nick}' not found.", err=True)
        raise typer.Exit(1)
    cascaded = config.remove_server(nick)
    if cascaded:
        noun = "collection" if len(cascaded) == 1 else "collections"
        typer.echo(f"Also removed {len(cascaded)} {noun}: {', '.join(cascaded)}.")
    typer.echo(f"Server '{nick}' removed.")
