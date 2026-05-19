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
from exist_shell.utils import check_xml_wellformed, handle_exist_errors, parse_target, resolve_collection


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
    allow_malformed: bool = typer.Option(False, "--allow-malformed", help="Upload even if the edited document is not well-formed XML."),
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
        last_seen = result.content

        while True:
            proc = subprocess.run(shlex.split(editor) + [str(tmp_path)])
            if proc.returncode != 0:
                typer.echo(f"Error: editor exited with code {proc.returncode}.", err=True)
                raise typer.Exit(1)

            new_content = tmp_path.read_bytes()

            if new_content == last_seen:
                if last_seen == result.content:
                    typer.echo("No changes.")
                else:
                    typer.echo("Aborted: document still has XML errors, not uploaded.", err=True)
                    raise typer.Exit(1)
                return

            if not allow_malformed:
                if xml_error := check_xml_wellformed(new_content, result.mime_type):
                    typer.echo(f"Warning: not well-formed XML: {xml_error}", err=True)
                    typer.echo("Fix the error and save to continue, or quit without changes to abort.", err=True)
                    typer.echo("Press Enter to re-open the editor...", err=True)
                    sys.stdin.readline()
                    last_seen = new_content
                    continue

            break

        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                client.put_document(full_path, new_content, result.mime_type)
        invalidate(nick)
    finally:
        tmp_path.unlink(missing_ok=True)
