"""put command — upload a document to an eXist collection path."""

import mimetypes
import sys
from pathlib import Path

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.config import Config
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError


def _resolve_mime(file: Path | None, mime: str | None) -> str:
    """Determine the MIME type to use for the upload.

    Args:
        file: Local file path, or None when reading from stdin.
        mime: Explicit MIME type from --mime flag, or None.

    Returns:
        Resolved MIME type string.
    """
    if mime is not None:
        return mime
    if file is not None:
        guessed, _ = mimetypes.guess_type(str(file))
        return guessed or "application/octet-stream"
    return "application/xml"


def put(
    target: str = typer.Argument(
        help="Collection and document path: <nick>:<path>.",
        autocompletion=collection_target_completer("any"),
    ),
    file: Path | None = typer.Option(None, "-f", "--file", help="Local file to upload (default: stdin)."),
    mime: str | None = typer.Option(None, "--mime", help="MIME type (default: application/xml, or guessed from file extension)."),
) -> None:
    """Upload a document to a collection path from a file or stdin."""
    nick, _, path = target.partition(":")
    if not path:
        typer.echo("Error: path is required (use <nick>:<path>).", err=True)
        raise typer.Exit(1)
    if not path.startswith("/"):
        path = "/" + path

    config = Config.load()
    if nick not in config.collections:
        typer.echo(f"Error: collection '{nick}' not found.", err=True)
        raise typer.Exit(1)

    collection = config.collections[nick]
    server = config.servers[collection.server_nick]
    full_path = f"/db/{collection.name}{path}"

    resolved_mime = _resolve_mime(file, mime)

    if file is not None:
        try:
            content = file.read_bytes()
        except OSError as e:
            typer.echo(f"Error: cannot read '{file}': {e}", err=True)
            raise typer.Exit(1)
    else:
        content = sys.stdin.buffer.read()

    try:
        with ExistClient(server) as client:
            client.put_document(full_path, content, resolved_mime)
    except ExistNotFoundError:
        typer.echo(f"Error: parent collection for '{path}' not found in '{nick}'.", err=True)
        raise typer.Exit(1)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{collection.server_nick}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
