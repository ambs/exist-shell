"""find command — locate documents by XPath predicate, with optional removal."""

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.exceptions import ExistQueryError
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def find(
    target: str = typer.Argument(
        help="Collection and path: <nick>[:<path>].",
        autocompletion=collection_target_completer("any"),
    ),
    query: str = typer.Option(
        ...,
        "--query",
        "-q",
        help='XPath expression evaluated recursively under the target (e.g. \'foo\\[@type="draft"]\').',
    ),
    remove: bool = typer.Option(False, "--remove", help="Delete matching documents instead of listing them."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt when used with --remove."),
) -> None:
    """Find documents whose content matches an XPath predicate, optionally deleting them."""
    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)
    prefix = f"/db/{collection.name}"

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                matches = client.find_documents(full_path, query)
                if not matches:
                    return
                if remove and not yes:
                    typer.confirm(f"Delete {len(matches)} matching document(s)?", abort=True)
                for doc_path in matches:
                    if remove:
                        client.delete_document(doc_path)
                    typer.echo(f"{nick}:{doc_path.removeprefix(prefix)}")
    except ExistQueryError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
