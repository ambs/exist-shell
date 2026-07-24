"""find command — locate documents by XPath expression, with optional removal."""

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.exceptions import ExistNotFoundError, ExistQueryError
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection

_QUERY_TIMEOUT = 120.0


def find(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=collection_target_completer("any"),
    ),
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help='XPath expression evaluated recursively under the target (e.g. \'foo\\[@type="draft"]\'). '
        "Embedded into a server-side XQuery without validation — only pass expressions you trust.",
    ),
    remove: bool = typer.Option(False, "--remove", help="Delete matching documents instead of listing them."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt when used with --remove."),
) -> None:
    """Find documents whose content matches an XPath expression, optionally deleting them.

    The ``--query`` expression is embedded into a server-side XQuery without
    validation or sandboxing, so it can execute arbitrary XQuery with the
    configured server credentials. Only pass expressions you trust; see
    ``docs/commands.md`` for details.
    """
    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)
    prefix = f"/db/{collection.name}"
    search_root = full_path.rstrip("/")

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server, read_timeout=_QUERY_TIMEOUT) as client:
                if not client.is_collection(search_root):
                    typer.echo(f"Error: path '{path}' not found in collection '{nick}'.", err=True)
                    raise typer.Exit(1)
                matches = client.find_documents(full_path, query)
                if not matches:
                    return
                if remove and not yes:
                    typer.confirm(f"Delete {len(matches)} matching document(s)?", abort=True)
                failures = 0
                for doc_path in matches:
                    if remove:
                        try:
                            client.delete_document(doc_path)
                        except ExistNotFoundError:
                            typer.echo(f"Warning: '{doc_path}' already gone, skipping.", err=True)
                            failures += 1
                            continue
                    typer.echo(f"{nick}:{doc_path.removeprefix(prefix)}")
                if remove:
                    invalidate(nick)
                if failures:
                    raise typer.Exit(1)
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
