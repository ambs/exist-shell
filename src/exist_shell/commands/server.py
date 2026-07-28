"""Server management commands (add, ls, rm, rename, status)."""

import re
import time
from dataclasses import dataclass

import typer

from pydantic import SecretStr

from exist_shell.client import ExistClient
from exist_shell.config import NICK_PATTERN, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistError

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


@dataclass(frozen=True)
class PingResult:
    """Outcome of a connectivity check against one server.

    Attributes:
        version: Server version string on success, ``None`` on failure.
        latency_ms: Round-trip time of the check in milliseconds.
        error: Short failure reason, ``None`` on success.
    """

    version: str | None
    latency_ms: int
    error: str | None

    @property
    def status(self) -> str:
        """Human-readable status field, e.g. ``OK (42ms)`` or ``FAIL (...)``.

        Returns:
            ``OK`` with the latency on success, ``FAIL`` with the reason
            otherwise.
        """
        if self.error is None:
            return f"OK ({self.latency_ms}ms)"
        return f"FAIL ({self.error})"


def _ping(server: Server) -> PingResult:
    """Ping a server and measure the round-trip latency.

    Args:
        server: The server configuration to check.

    Returns:
        The :class:`PingResult` of the check.
    """
    start = time.perf_counter()
    version: str | None = None
    error: str | None = None
    try:
        with ExistClient(server) as client:
            version = client.server_version()
    except ExistAuthError:
        error = "authentication failed"
    except ExistConnectionError as e:
        error = f"cannot connect: {e.cause}"
    except ExistError as e:
        error = str(e)
    latency_ms = round((time.perf_counter() - start) * 1000)
    return PingResult(version=version, latency_ms=latency_ms, error=error)


@app.command("status")
def server_status(
    nick: str | None = typer.Argument(
        None,
        help="Server nickname (default: check all configured servers).",
        autocompletion=_complete_server_nick,
    ),
) -> None:
    """Check server connectivity, reporting version and latency (all servers if no nick)."""
    config = Config.load()
    if not config.servers:
        typer.echo("Error: no servers configured.", err=True)
        raise typer.Exit(1)

    if nick is not None:
        if nick not in config.servers:
            typer.echo(f"Error: server nick '{nick}' not found.", err=True)
            raise typer.Exit(1)
        server = config.servers[nick]
        result = _ping(server)
        typer.echo(f"Server:   {server.base_url}")
        typer.echo(f"Version:  {result.version or '-'}")
        typer.echo(f"Status:   {result.status}")
        if result.error is not None:
            raise typer.Exit(1)
        return

    rows: list[tuple[str, str, str, str]] = []
    failed = False
    for server_nick, server in config.servers.items():
        result = _ping(server)
        failed = failed or result.error is not None
        rows.append((server_nick, server.base_url, result.version or "-", result.status))

    widths = [max(len(row[col]) for row in rows) for col in range(len(rows[0]))]
    for row in rows:
        padded = "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row[:-1]))
        typer.echo(f"{padded}  {row[-1]}")
    if failed:
        raise typer.Exit(1)


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
