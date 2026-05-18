"""mv command — move or rename a document or collection on an eXist server."""

from pathlib import PurePosixPath

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.models import CollectionEntry
from exist_shell.utils import handle_exist_errors, is_remote, parse_target, resolve_collection


def _dest_path(target_path: str, source_name: str) -> str:
    """Resolve the destination path, appending source name when target ends with '/'.

    Args:
        target_path: The path component of the target argument.
        source_name: Name to append when path ends with '/'.

    Returns:
        Final destination path without a trailing slash.
    """
    if target_path.endswith("/"):
        return target_path.rstrip("/") + "/" + source_name
    return target_path


def _collect_docs(client: ExistClient, base: str, rel_prefix: str = "") -> list[tuple[str, str]]:
    """Recursively collect all (rel_path, full_path) document pairs under base.

    Args:
        client: Active ExistClient.
        base: Full eXist path to walk.
        rel_prefix: Relative path prefix accumulated during recursion.

    Returns:
        List of (relative_path, full_path) tuples for every document found.
    """
    items = client.list_collection(base)
    result: list[tuple[str, str]] = []
    for item in items:
        rel = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
        if isinstance(item, CollectionEntry):
            result.extend(_collect_docs(client, f"{base}/{item.name}", rel))
        else:
            result.append((rel, f"{base}/{item.name}"))
    return result


def _copy_then_delete_collection(client: ExistClient, src: str, dst: str) -> None:
    """Move a collection via REST: copy all contents first, then delete the source.

    All documents and subcollections are created at the destination before any
    deletion, so a partial failure leaves the source intact.

    Args:
        client: Active ExistClient.
        src: Full eXist path of the source collection.
        dst: Full eXist path of the destination collection.
    """
    docs = _collect_docs(client, src)

    # Create destination root and any needed subcollection paths.
    # create_collection is idempotent and handles intermediate levels.
    client.create_collection(dst)
    seen: set[str] = set()
    for rel_path, _ in docs:
        parent = str(PurePosixPath(rel_path).parent)
        if parent != "." and parent not in seen:
            client.create_collection(f"{dst}/{parent}")
            seen.add(parent)

    # Upload all documents (add-before-remove).
    for rel_path, src_full_path in docs:
        doc = client.get_document(src_full_path)
        client.put_document(f"{dst}/{rel_path}", doc.content, doc.mime_type)

    # Delete source only after all uploads succeed.
    client.delete_collection(src)


def mv(
    source: str = typer.Argument(
        help="Source remote path: <nick>:<path>.",
        autocompletion=collection_target_completer("any"),
    ),
    target: str = typer.Argument(
        help="Target remote path: <nick>:<path>. Trailing '/' moves source into that collection.",
        autocompletion=collection_target_completer("any"),
    ),
) -> None:
    """Move or rename a document or collection on the server."""
    if not is_remote(source) or not is_remote(target):
        typer.echo(
            "Error: both source and target must be remote paths (nick:path).",
            err=True,
        )
        raise typer.Exit(1)

    src_nick, src_path = parse_target(source)
    src_collection, src_server, src_full = resolve_collection(src_nick, src_path)

    tgt_nick, tgt_path = parse_target(target)
    resolved_dest = _dest_path(tgt_path, PurePosixPath(src_path).name)
    tgt_collection, tgt_server, tgt_full = resolve_collection(tgt_nick, resolved_dest)

    if src_server.host != tgt_server.host or src_server.port != tgt_server.port:
        typer.echo(
            "Error: cross-server mv is not supported. Use cp + rm instead.",
            err=True,
        )
        raise typer.Exit(1)

    with handle_exist_errors(src_path, src_nick, src_collection.server_nick):
        with ExistClient(src_server) as client:
            if client.is_collection(src_full):
                _copy_then_delete_collection(client, src_full, tgt_full)
            else:
                client.move_document(src_full, tgt_full)

    invalidate(src_nick)
    if tgt_nick != src_nick:
        invalidate(tgt_nick)
