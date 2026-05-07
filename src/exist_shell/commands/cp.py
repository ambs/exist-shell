"""cp command — copy documents between local paths and remote eXist collections."""

from pathlib import Path, PurePosixPath

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.utils import guess_mime, handle_exist_errors, is_remote, parse_target, resolve_collection


def _remote_dest(path: str, source_name: str) -> str:
    """Resolve the final remote destination path.

    Args:
        path: The target path as typed (may end with ``/`` to signal a directory).
        source_name: Filename to append when path ends with ``/``.

    Returns:
        Final destination path without a trailing slash.
    """
    if path.endswith("/"):
        return path.rstrip("/") + "/" + source_name
    return path


def _local_dest(target: str, source_name: str) -> Path:
    """Resolve the final local destination path.

    Args:
        target: Local target path as typed.
        source_name: Filename to append when target is an existing directory.

    Returns:
        Resolved local Path for writing.
    """
    p = Path(target)
    if p.is_dir():
        return p / source_name
    return p


def _local_to_remote(source: str, target: str) -> None:
    """Copy a local file to a remote eXist path.

    Args:
        source: Local file path.
        target: Remote ``nick:path`` destination.
    """
    src_path = Path(source)
    try:
        content = src_path.read_bytes()
    except OSError as e:
        typer.echo(f"Error: cannot read '{source}': {e}", err=True)
        raise typer.Exit(1)

    mime_type = guess_mime(src_path)

    nick, tgt_path = parse_target(target)
    dest_path = _remote_dest(tgt_path, src_path.name)
    collection, server, full_dest = resolve_collection(nick, dest_path)

    with handle_exist_errors(dest_path, nick, collection.server_nick):
        with ExistClient(server) as client:
            client.put_document(full_dest, content, mime_type)
    invalidate(nick)


def _remote_to_local(source: str, target: str) -> None:
    """Copy a remote eXist document to a local path.

    Args:
        source: Remote ``nick:path`` source.
        target: Local file or directory path.
    """
    nick, src_path = parse_target(source)
    collection, server, full_src = resolve_collection(nick, src_path)

    with handle_exist_errors(src_path, nick, collection.server_nick):
        with ExistClient(server) as client:
            result = client.get_document(full_src)

    dest = _local_dest(target, PurePosixPath(src_path).name)
    try:
        dest.write_bytes(result.content)
    except OSError as e:
        typer.echo(f"Error: cannot write '{dest}': {e}", err=True)
        raise typer.Exit(1)


def _remote_to_remote(source: str, target: str) -> None:
    """Copy a remote eXist document to another remote eXist path.

    Args:
        source: Remote ``nick:path`` source.
        target: Remote ``nick:path`` destination (may be a different collection or server).
    """
    src_nick, src_path = parse_target(source)
    src_collection, src_server, src_full = resolve_collection(src_nick, src_path)

    with handle_exist_errors(src_path, src_nick, src_collection.server_nick):
        with ExistClient(src_server) as client:
            result = client.get_document(src_full)

    tgt_nick, tgt_path = parse_target(target)
    dest_path = _remote_dest(tgt_path, PurePosixPath(src_path).name)
    tgt_collection, tgt_server, tgt_full = resolve_collection(tgt_nick, dest_path)

    with handle_exist_errors(dest_path, tgt_nick, tgt_collection.server_nick):
        with ExistClient(tgt_server) as client:
            client.put_document(tgt_full, result.content, result.mime_type)
    invalidate(tgt_nick)


def cp(
    source: str = typer.Argument(
        help="Source: remote ``<nick>:<path>`` or local file path.",
        autocompletion=collection_target_completer("resource", allow_local=True),
    ),
    target: str = typer.Argument(
        help="Target: remote ``<nick>:<path>`` or local path (file or directory).",
        autocompletion=collection_target_completer("any", allow_local=True),
    ),
) -> None:
    """Copy a document between local paths and remote eXist collections."""
    src_remote = is_remote(source)
    tgt_remote = is_remote(target)

    if not src_remote and not tgt_remote:
        typer.echo(
            "Error: at least one of source or target must be a remote path (nick:path).",
            err=True,
        )
        raise typer.Exit(1)

    if src_remote and tgt_remote:
        _remote_to_remote(source, target)
    elif src_remote:
        _remote_to_local(source, target)
    else:
        _local_to_remote(source, target)
