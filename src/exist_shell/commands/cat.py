"""cat command — print document content from an eXist collection path."""

import sys

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection

_TEXT_TYPES = {"application/xml", "application/json", "application/javascript", "application/xquery"}


def _is_text(mime_type: str) -> bool:
    """Return True if the MIME type should be treated as human-readable text.

    Args:
        mime_type: The MIME type string (without parameters).

    Returns:
        True if the content is printable text, False if binary.
    """
    return mime_type.startswith("text/") or mime_type in _TEXT_TYPES


def cat(
    target: str = typer.Argument(
        help="Collection and document path: <nick>:<path>.",
        autocompletion=collection_target_completer("resource"),
    ),
    raw: bool = typer.Option(False, "--raw", help="Write raw bytes to stdout even for binary content."),
) -> None:
    """Print the content of a document to stdout."""
    nick, path = parse_target(target)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            result = client.get_document(full_path)

    if not raw and not _is_text(result.mime_type):
        typer.echo(
            f"Error: '{path}' is binary ({result.mime_type}). Use --raw to write bytes to stdout.",
            err=True,
        )
        raise typer.Exit(1)

    if raw:
        sys.stdout.buffer.write(result.content)
    else:
        sys.stdout.write(result.content.decode())
