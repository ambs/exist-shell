import typer

from pydantic import SecretStr

from exist_shell.client import ExistClient
from exist_shell.config import Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError

app = typer.Typer(help="Manage servers.", no_args_is_help=True)


def _default_nick(host: str) -> str:
    return host.split(".")[0]


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
