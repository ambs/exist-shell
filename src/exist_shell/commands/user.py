"""User management commands (ls, add, rm, info)."""

import typer

from exist_shell.client import ExistClient
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError

app = typer.Typer(help="Manage eXist-db users.", no_args_is_help=True)


@app.command("ls")
def user_ls(
    server: str | None = typer.Option(None, "--server", help="Server nick to query."),
) -> None:
    """List all user accounts and their group memberships.

    Args:
        server: Server nick to query. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    config = Config.load()
    if not config.servers:
        typer.echo("Error: no servers configured. Use 'exsh server add' first.", err=True)
        raise typer.Exit(1)
    if server is None:
        if len(config.servers) != 1:
            typer.echo("Error: --server is required when multiple servers are configured.", err=True)
            raise typer.Exit(1)
        server = next(iter(config.servers))
    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)

    try:
        with ExistClient(config.servers[server]) as client:
            users = client.list_users()
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    for u in users:
        typer.echo(f"{u.username}\t{', '.join(u.groups)}")


@app.command("add")
def user_add(
    username: str = typer.Argument(help="Account name to create."),
    group: str = typer.Option("guest", "--group", help="Comma-separated group names. The first is the primary group."),
    password: str | None = typer.Option(None, "--password", help="Password (prompted if omitted)."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target."),
) -> None:
    """Create a new user account on the server.

    Prompts for a password when ``--password`` is not supplied so the
    credential is never written to the shell history.

    Args:
        username: The new account name.
        group: Comma-separated group names. The first becomes the primary group.
            Defaults to ``guest``.
        password: Plaintext password. Prompted interactively when omitted.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    config = Config.load()
    if not config.servers:
        typer.echo("Error: no servers configured. Use 'exsh server add' first.", err=True)
        raise typer.Exit(1)
    if server is None:
        if len(config.servers) != 1:
            typer.echo("Error: --server is required when multiple servers are configured.", err=True)
            raise typer.Exit(1)
        server = next(iter(config.servers))
    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)

    groups = [g.strip() for g in group.split(",") if g.strip()]
    if not groups:
        typer.echo("Error: at least one group is required.", err=True)
        raise typer.Exit(1)

    if password is None:
        password = typer.prompt(f"Password for '{username}'", hide_input=True, confirmation_prompt=True)

    try:
        with ExistClient(config.servers[server]) as client:
            client.create_user(username, password, groups)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"User '{username}' created.")


@app.command("rm")
def user_rm(
    username: str = typer.Argument(help="Account name to remove."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    server: str | None = typer.Option(None, "--server", help="Server nick to target."),
) -> None:
    """Remove a user account from the server.

    Prompts for confirmation unless ``--yes`` is supplied.

    Args:
        username: The account name to remove.
        yes: When True, skip the confirmation prompt.
        server: Server nick to target. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    config = Config.load()
    if not config.servers:
        typer.echo("Error: no servers configured. Use 'exsh server add' first.", err=True)
        raise typer.Exit(1)
    if server is None:
        if len(config.servers) != 1:
            typer.echo("Error: --server is required when multiple servers are configured.", err=True)
            raise typer.Exit(1)
        server = next(iter(config.servers))
    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)

    if not yes:
        typer.confirm(f"Remove user '{username}'?", abort=True)

    try:
        with ExistClient(config.servers[server]) as client:
            client.delete_user(username)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"User '{username}' removed.")


@app.command("info")
def user_info(
    username: str = typer.Argument(help="Account name to inspect."),
    server: str | None = typer.Option(None, "--server", help="Server nick to query."),
) -> None:
    """Show detailed information about a user account.

    Args:
        username: The account name to inspect.
        server: Server nick to query. Auto-selected when only one server is
            configured; required when multiple servers are configured.
    """
    config = Config.load()
    if not config.servers:
        typer.echo("Error: no servers configured. Use 'exsh server add' first.", err=True)
        raise typer.Exit(1)
    if server is None:
        if len(config.servers) != 1:
            typer.echo("Error: --server is required when multiple servers are configured.", err=True)
            raise typer.Exit(1)
        server = next(iter(config.servers))
    if server not in config.servers:
        typer.echo(f"Error: server '{server}' not found.", err=True)
        raise typer.Exit(1)

    try:
        with ExistClient(config.servers[server]) as client:
            info = client.get_user(username)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server}'.", err=True)
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
