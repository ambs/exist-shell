"""edit command — download, edit locally, and re-upload a document."""

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection


def _find_editor() -> str:
    """Return the editor command from $VISUAL, $EDITOR, or a platform default.

    Returns:
        Editor command string (may include flags, e.g. ``code --wait``).
    """
    for var in ("VISUAL", "EDITOR"):
        val = os.environ.get(var, "").strip()
        if val:
            return val
    return "notepad" if sys.platform == "win32" else "vi"


def edit(
    target: str = typer.Argument(
        help="Collection and document path: <nick>:<path>.",
        autocompletion=collection_target_completer("resource"),
    ),
) -> None:
    """Download a document, open it in $VISUAL/$EDITOR, and re-upload if changed."""
    nick, path = parse_target(target)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            result = client.get_document(full_path)

    suffix = PurePosixPath(path).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        tmp.write(result.content)

    try:
        editor = _find_editor()
        proc = subprocess.run(shlex.split(editor) + [str(tmp_path)])
        if proc.returncode != 0:
            typer.echo(f"Error: editor exited with code {proc.returncode}.", err=True)
            raise typer.Exit(1)

        new_content = tmp_path.read_bytes()
        if new_content == result.content:
            typer.echo("No changes.")
            return

        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                client.put_document(full_path, new_content, result.mime_type)
        invalidate(nick)
    finally:
        tmp_path.unlink(missing_ok=True)
