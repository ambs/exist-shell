"""exec command — execute an XQuery script on an eXist-db server."""

import sys
from pathlib import Path

import typer

from exist_shell.client import ExistClient
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection
from exist_shell.xquery import list_validators, preprocess, validate_locally


def _parse_params(raw: list[str]) -> dict[str, str]:
    """Parse repeated ``name=value`` strings into a dict.

    Args:
        raw: Values collected from repeated ``-p/--param`` options.

    Returns:
        Mapping of parameter name to value.
    """
    params = {}
    for item in raw:
        name, sep, value = item.partition("=")
        if not sep:
            typer.echo(f"Error: invalid --param '{item}' (expected name=value).", err=True)
            raise typer.Exit(1)
        params[name] = value
    return params


def exec(
    target: str | None = typer.Argument(
        default=None,
        help="Collection context for the query: <nick>[:<path>].",
    ),
    resource: str | None = typer.Option(
        None, "--resource", help="Execute a stored resource in place instead of local code: <nick>:<path.xql>."
    ),
    param: list[str] = typer.Option(
        [], "-p", "--param", help="Query-string parameter to forward with --resource, as name=value (repeatable)."
    ),
    file: Path | None = typer.Option(None, "-f", "--file", help="XQuery file to execute (default: stdin)."),
    no_fix: bool = typer.Option(False, "--no-fix", help="Skip XQuery preprocessing (version declaration, namespace imports)."),
    no_validate: bool = typer.Option(False, "--no-validate", help="Skip local validation even if a validator is installed."),
    validator: str | None = typer.Option(None, "--validator", help="Name of the local validator to use (default: first installed)."),
    list_validators_flag: bool = typer.Option(False, "--list-validators", help="List known validators and their install status, then exit."),
) -> None:
    """Execute an XQuery script on an eXist-db server and print the result."""
    if list_validators_flag:
        for name, path in list_validators():
            status = path or "not installed"
            typer.echo(f"{name:12}{status}")
        raise typer.Exit()

    if resource is not None:
        if target is not None:
            typer.echo("Error: TARGET and --resource are mutually exclusive.", err=True)
            raise typer.Exit(1)
        nick, path = parse_target(resource)
        collection, server, full_path = resolve_collection(nick, path)
        params = _parse_params(param)
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                output = client.execute_resource(full_path, params=params or None)
        typer.echo(output, nl=False)
        raise typer.Exit()

    if param:
        typer.echo("Error: --param requires --resource.", err=True)
        raise typer.Exit(1)

    if target is None:
        typer.echo("Error: missing argument 'TARGET'.", err=True)
        raise typer.Exit(1)

    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)

    if file is not None:
        try:
            code = file.read_text(encoding="utf-8")
        except OSError as e:
            typer.echo(f"Error: cannot read '{file}': {e}", err=True)
            raise typer.Exit(1)
    else:
        code = sys.stdin.read()

    if not no_fix:
        code = preprocess(code)

    if not no_validate:
        result = validate_locally(code, validator=validator)
        if not result.ok:
            typer.echo(f"Error: {result.error}", err=True)
            raise typer.Exit(1)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            output = client.execute_query(code, context=full_path)

    typer.echo(output, nl=False)
