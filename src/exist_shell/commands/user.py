"""User management commands (ls, add, rm, info, passwd)."""

import sys

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import server_at_completer, server_nick_completer, user_arg_completer
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
from exist_shell.utils import parse_user_at_server

app = typer.Typer(help="Manage eXist-db users.", no_args_is_help=True)


def _resolve_server(
    config: Config,
    inline_server: str | None,
    flag_server: str | None,
) -> str:
    """Resolve the effective server nick from an inline @server and --server flag.

    Args:
        config: The loaded configuration.
        inline_server: Server nick extracted from a ``user@server`` or ``@server``
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
def user_ls(
    at_server: str | None = typer.Argument(None, metavar="@SERVER", help="Server in @nick form (e.g. @prod).", autocompletion=server_at_completer),
    server: str | None = typer.Option(None, "--server", help="Server nick to query.", autocompletion=server_nick_completer),
) -> None:
    """List all user accounts and their group memberships.

    The server may be specified as a bare ``@nick`` positional argument
    (e.g. ``user ls @prod``) or via ``--server``.  When omitted and only one
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
            users = client.list_users()
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    for u in users:
        typer.echo(f"{u.username}\t{', '.join(u.groups)}")


@app.command("add")
def user_add(
    username: str = typer.Argument(help="Account name to create, optionally as user@server.", autocompletion=user_arg_completer),
    group: str = typer.Option("guest", "--group", help="Comma-separated group names. The first is the primary group."),
    password: str | None = typer.Option(None, "--password", help="Password (prompted if omitted)."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target.", autocompletion=server_nick_completer),
) -> None:
    """Create a new user account on the server.

    The username may include an inline server nick using ``user@server``
    syntax (e.g. ``alice@prod``).  Prompts for a password when ``--password``
    is not supplied so the credential is never written to the shell history.

    Args:
        username: The new account name, optionally suffixed with ``@server_nick``.
        group: Comma-separated group names. The first becomes the primary group.
            Defaults to ``guest``.
        password: Plaintext password. Prompted interactively when omitted.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_username, inline_server = parse_user_at_server(username)
    if not bare_username:
        typer.echo("Error: username cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    groups = [g.strip() for g in group.split(",") if g.strip()]
    if not groups:
        typer.echo("Error: at least one group is required.", err=True)
        raise typer.Exit(1)

    if password is None:
        password = typer.prompt(f"Password for '{bare_username}'", hide_input=True, confirmation_prompt=True)

    try:
        with ExistClient(config.servers[resolved]) as client:
            client.create_user(bare_username, password, groups)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"User '{bare_username}' created.")


@app.command("rm")
def user_rm(
    username: str = typer.Argument(help="Account name to remove, optionally as user@server.", autocompletion=user_arg_completer),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target.", autocompletion=server_nick_completer),
) -> None:
    """Remove a user account from the server.

    The username may include an inline server nick using ``user@server``
    syntax (e.g. ``alice@prod``).  Prompts for confirmation unless ``--yes``
    is supplied.

    Args:
        username: The account name to remove, optionally suffixed with ``@server_nick``.
        yes: When True, skip the confirmation prompt.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_username, inline_server = parse_user_at_server(username)
    if not bare_username:
        typer.echo("Error: username cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    if not yes:
        typer.confirm(f"Remove user '{bare_username}'?", abort=True)

    try:
        with ExistClient(config.servers[resolved]) as client:
            client.delete_user(bare_username)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"User '{bare_username}' removed.")


@app.command("info")
def user_info(
    username: str = typer.Argument(help="Account name to inspect, optionally as user@server.", autocompletion=user_arg_completer),
    server: str | None = typer.Option(None, "--server", help="Server nick to query.", autocompletion=server_nick_completer),
) -> None:
    """Show detailed information about a user account.

    The username may include an inline server nick using ``user@server``
    syntax (e.g. ``alice@prod``).

    Args:
        username: The account name to inspect, optionally suffixed with ``@server_nick``.
        server: Server nick to query. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_username, inline_server = parse_user_at_server(username)
    if not bare_username:
        typer.echo("Error: username cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    try:
        with ExistClient(config.servers[resolved]) as client:
            info = client.get_user(bare_username)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Username: {info.username}")
    if info.full_name:
        typer.echo(f"Full name: {info.full_name}")
    typer.echo(f"Groups:   {', '.join(info.groups)}")
    typer.echo(f"Enabled:  {info.enabled}")


@app.command("passwd")
def user_passwd(
    username: str = typer.Argument(help="Account name, optionally as user@server.", autocompletion=user_arg_completer),
    from_stdin: bool = typer.Option(False, "--stdin", help="Read new password from stdin (for scripting)."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target.", autocompletion=server_nick_completer),
) -> None:
    """Change a user's password on the server.

    The username may include an inline server nick using ``user@server``
    syntax (e.g. ``alice@prod``).  Prompts for the new password interactively
    (with confirmation) unless ``--stdin`` is supplied, in which case the
    password is read from standard input — suitable for piped automation.
    The password is never accepted on the command line to avoid shell history
    exposure.

    Args:
        username: The account name, optionally suffixed with ``@server_nick``.
        from_stdin: When True, read the new password from stdin instead of
            prompting interactively.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    bare_username, inline_server = parse_user_at_server(username)
    if not bare_username:
        typer.echo("Error: username cannot be empty.", err=True)
        raise typer.Exit(1)

    config = Config.load()
    resolved = _resolve_server(config, inline_server, server)

    if from_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        password = typer.prompt(f"New password for '{bare_username}'", hide_input=True, confirmation_prompt=True)

    try:
        with ExistClient(config.servers[resolved]) as client:
            client.change_password(bare_username, password)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{resolved}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Password for '{bare_username}' updated.")
