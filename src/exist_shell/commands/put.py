"""put command — upload a document to an eXist collection path."""

import sys
from pathlib import Path

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import check_xml_wellformed, guess_mime, handle_exist_errors, parse_target, resolve_collection


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
        return guess_mime(file)
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
    nick, path = parse_target(target)
    collection, server, full_path = resolve_collection(nick, path)
    resolved_mime = _resolve_mime(file, mime)

    if file is not None:
        try:
            content = file.read_bytes()
        except OSError as e:
            typer.echo(f"Error: cannot read '{file}': {e}", err=True)
            raise typer.Exit(1)
    else:
        content = sys.stdin.buffer.read()

    if xml_error := check_xml_wellformed(content, resolved_mime):
        source = str(file) if file is not None else "stdin"
        typer.echo(f"Error: '{source}' is not well-formed XML: {xml_error}", err=True)
        raise typer.Exit(1)

    # PUT silently overwrites existing documents. A --no-clobber flag could
    # check existence first (HEAD request) and abort if the resource is found.
    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            client.put_document(full_path, content, resolved_mime)
    invalidate(nick)
