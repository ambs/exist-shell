"""Group management commands (ls, list, add, rm)."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import server_at_completer, server_nick_completer, user_arg_completer
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.utils import parse_user_at_server

app = typer.Typer(help="Manage eXist-db groups.", no_args_is_help=True)


def _resolve_server(
    config: Config,
    inline_server: str | None,
    flag_server: str | None,
) -> str:
    """Resolve the effective server nick from an inline @server and --server flag.

    Args:
        config: The loaded configuration.
        inline_server: Server nick extracted from a ``group@server`` or ``@server``
            argument; ``None`` if no ``@`` suffix was present.
        flag_server: Server nick provided via the ``--server`` option; ``None``
            if the flag was omitted.

    Returns:
        The resolved server nick, guaranteed to exist in ``config.servers``.

    Raises:
        typer.Exit: If both sources conflict, no server can be determined, or
            the resolved nick does not exist in the configuration.
    """
    if not config.servers:
        typer.echo("Error: no servers configured. Use 'exsh server add' first.", err=True)
        raise typer.Exit(1)
    if inline_server and flag_server:
        typer.echo(
            "Error: conflicting server specifications: use @server or --server, not both.",
            err=True,
        )
        raise typer.Exit(1)
    server = inline_server or flag_server
    if server is None:
        if len(config.servers) != 1:
            typer.echo(
                "Error: --server is required when multiple servers are configured.",
                err=True,
            )
            raise typer.Exit(1)
        server = next(iter(config.servers))
    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)
    return server


@app.command("ls")
def group_ls(
    at_server: str | None = typer.Argument(None, metavar="@SERVER", help="Server in @nick form (e.g. @prod).", autocompletion=server_at_completer),
    server: str | None = typer.Option(None, "--server", help="Server nick to query.", autocompletion=server_nick_completer),
) -> None:
    """List all groups and their members.

    The server may be specified as a bare ``@nick`` positional argument
    (e.g. ``group ls @prod``) or via ``--server``.  When omitted and only one
    server is configured it is selected automatically.

    Args:
        at_server: Optional server nick in ``@nick`` form.
        server: Server nick to query. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    inline_server: str | None = None
    if at_server is not None:
        if not at_server.startswith("@"):
            typer.echo("Error: positional server argument must be in @nick form (e.g. @prod).", err=True)
            raise typer.Exit(1)
        inline_server = at_server[1:]
        if not inline_server:
            typer.echo("Error: server nick cannot be empty.", err=True)
            raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    try:
        with ExistClient(config.servers[resolved]) as client:
            groups = client.list_groups()
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    for g in groups:
        typer.echo(f"{g.name}\t{', '.join(g.members)}")


@app.command("add")
def group_add(
    groupname: str = typer.Argument(help="Group name to create, optionally as group@server.", autocompletion=user_arg_completer),
    server: str | None = typer.Option(None, "--server", help="Server nick to target.", autocompletion=server_nick_completer),
) -> None:
    """Create a new group on the server.

    The group name may include an inline server nick using ``group@server``
    syntax (e.g. ``editors@prod``).

    Args:
        groupname: The new group name, optionally suffixed with ``@server_nick``.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_groupname, inline_server = parse_user_at_server(groupname)
    if not bare_groupname:
        typer.echo("Error: group name cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    try:
        with ExistClient(config.servers[resolved]) as client:
            client.create_group(bare_groupname)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Group '{bare_groupname}' created.")


@app.command("rm")
def group_rm(
    groupname: str = typer.Argument(help="Group name to remove, optionally as group@server.", autocompletion=user_arg_completer),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target.", autocompletion=server_nick_completer),
) -> None:
    """Remove a group from the server.

    The group name may include an inline server nick using ``group@server``
    syntax (e.g. ``editors@prod``).  Prompts for confirmation unless ``--yes``
    is supplied.

    Args:
        groupname: The group name to remove, optionally suffixed with ``@server_nick``.
        yes: When True, skip the confirmation prompt.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_groupname, inline_server = parse_user_at_server(groupname)
    if not bare_groupname:
        typer.echo("Error: group name cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    if not yes:
        typer.confirm(f"Remove group '{bare_groupname}'?", abort=True)

    try:
        with ExistClient(config.servers[resolved]) as client:
            client.delete_group(bare_groupname)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Group '{bare_groupname}' removed.")
