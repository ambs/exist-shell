"""cat command — print document content from an eXist collection path."""

import sys

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.utils import validate_path

_TEXT_TYPES = {"text/", "application/xml", "application/json", "application/javascript"}


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
    nick, _, path = target.partition(":")
    if not path:
        typer.echo("Error: path is required (use <nick>:<path>).", err=True)
        raise typer.Exit(1)
    if not path.startswith("/"):
        path = "/" + path

    try:
        validate_path(path)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    config = Config.load()
    if nick not in config.collections:
        typer.echo(f"Error: collection '{nick}' not found.", err=True)
        raise typer.Exit(1)

    collection = config.collections[nick]
    server = config.servers[collection.server_nick]
    full_path = f"/db/{collection.name}{path}"

    try:
        with ExistClient(server) as client:
            result = client.get_document(full_path)
    except ExistNotFoundError:
        typer.echo(f"Error: path '{path}' not found in collection '{nick}'.", err=True)
        raise typer.Exit(1)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{collection.server_nick}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

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
