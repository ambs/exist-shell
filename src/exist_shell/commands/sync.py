"""sync command — sync a local folder with a remote eXist collection."""

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import NamedTuple

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.config import Config
from exist_shell.models import CollectionEntry, ResourceEntry
from exist_shell.utils import (
    guess_mime,
    handle_exist_errors,
    is_remote,
    parse_target,
    resolve_collection,
)


def _get_sync_cache_dir() -> Path:
    """Return the sync manifest cache directory, resolved from the active config.

    Returns:
        Path to the sync cache directory.
    """
    return Config.load().resolved_cache_dir() / "sync"


class SyncAction(Enum):
    """Outcome of a single-file sync decision."""

    UPLOADED = "uploaded"
    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    CONFLICT = "conflict"
    DELETED = "deleted"
    CREATED = "created"


class RemoteResource(NamedTuple):
    """A resource found during a remote tree walk.

    Attributes:
        rel_path: Path relative to the sync root, using ``/`` as separator.
        entry: The ResourceEntry returned by the REST listing.
    """

    rel_path: str
    entry: ResourceEntry


class RemoteTree(NamedTuple):
    """Result of a recursive remote tree walk.

    Attributes:
        resources: All resources found, with paths relative to the walk root.
        subcollections: Relative paths of all subcollections found.
    """

    resources: list[RemoteResource]
    subcollections: list[str]


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's contents.

    Args:
        path: Local file to hash.

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_path(nick: str, remote_path: str) -> Path:
    """Return the manifest file path for a (nick, remote_path) pair.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.

    Returns:
        Absolute path to the JSON manifest file.
    """
    key = hashlib.sha256(remote_path.encode()).hexdigest()[:16]
    return _get_sync_cache_dir() / f"{nick}@{key}.json"


def _load_manifest(nick: str, remote_path: str) -> dict[str, dict]:
    """Load the sync manifest, returning an empty dict if the file is missing.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.

    Returns:
        Dict mapping relative file path to its last-synced state.
    """
    p = _manifest_path(nick, remote_path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def _save_manifest(nick: str, remote_path: str, manifest: dict[str, dict]) -> None:
    """Atomically write the sync manifest to disk.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.
        manifest: Dict mapping relative file path to its last-synced state.
    """
    p = _manifest_path(nick, remote_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.rename(p)


def _walk_remote(client: ExistClient, base_path: str) -> RemoteTree:
    """Recursively list all resources and subcollections under a remote path.

    Args:
        client: Active ExistClient.
        base_path: Full eXist path to walk (e.g. ``/db/myapp/reports``).

    Returns:
        RemoteTree with resources and subcollections relative to ``base_path``.
    """
    items = client.list_collection(base_path)
    resources: list[RemoteResource] = []
    subcollections: list[str] = []
    for item in items:
        if isinstance(item, CollectionEntry):
            subcollections.append(item.name)
            subtree = _walk_remote(client, f"{base_path}/{item.name}")
            resources.extend(
                RemoteResource(f"{item.name}/{r.rel_path}", r.entry) for r in subtree.resources
            )
            subcollections.extend(f"{item.name}/{c}" for c in subtree.subcollections)
        else:
            resources.append(RemoteResource(item.name, item))
    return RemoteTree(resources, subcollections)


def _push_file(
    client: ExistClient,
    full_path: str,
    local_file: Path,
    rel: str,
    remote_mtime: str,
    manifest: dict[str, dict],
    force: bool,
    dry_run: bool,
) -> SyncAction:
    """Decide and execute the push action for a single file.

    Stores an empty ``remote_last_modified`` after upload; callers must
    re-list the remote collection afterwards to record the server-assigned mtime.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection (e.g. ``/db/myapp``).
        local_file: Local file to upload.
        rel: Relative path of the file within the sync tree.
        remote_mtime: Current ``last_modified`` from the remote listing.
        manifest: Sync manifest (mutated in place on upload).
        force: If True, upload regardless of manifest state.
        dry_run: If True, do not perform the upload.

    Returns:
        The SyncAction taken.
    """

    def _upload(local_hash: str) -> None:
        if not dry_run:
            client.put_document(
                f"{full_path}/{rel}",
                local_file.read_bytes(),
                guess_mime(local_file, "application/xml"),
            )
            manifest[rel] = {"local_sha256": local_hash, "remote_last_modified": ""}

    entry = manifest.get(rel, {})

    if force or rel not in manifest:
        _upload(_sha256(local_file))
        return SyncAction.UPLOADED

    local_hash = _sha256(local_file)
    local_changed = local_hash != entry.get("local_sha256", "")
    remote_changed = remote_mtime != entry.get("remote_last_modified", "")

    if local_changed and remote_changed:
        return SyncAction.CONFLICT

    if local_changed:
        _upload(local_hash)
        return SyncAction.UPLOADED

    return SyncAction.SKIPPED


def _pull_file(
    client: ExistClient,
    full_path: str,
    dest: Path,
    rel: str,
    remote_mtime: str,
    manifest: dict[str, dict],
    force: bool,
    dry_run: bool,
) -> SyncAction:
    """Decide and execute the pull action for a single file.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection (e.g. ``/db/myapp``).
        dest: Local directory to pull into.
        rel: Relative path of the file within the sync tree.
        remote_mtime: Current ``last_modified`` from the remote listing.
        manifest: Sync manifest (mutated in place on download).
        force: If True, download regardless of manifest state.
        dry_run: If True, do not perform the download.

    Returns:
        The SyncAction taken.
    """
    local_file = dest / rel

    def _download() -> None:
        if not dry_run:
            result = client.get_document(f"{full_path}/{rel}")
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_bytes(result.content)
            manifest[rel] = {
                "local_sha256": _sha256(local_file),
                "remote_last_modified": remote_mtime,
            }

    entry = manifest.get(rel, {})

    if force or rel not in manifest:
        _download()
        return SyncAction.DOWNLOADED

    remote_changed = remote_mtime != entry.get("remote_last_modified", "")

    if not remote_changed:
        if not local_file.exists():
            _download()
            return SyncAction.DOWNLOADED
        return SyncAction.SKIPPED

    local_hash = _sha256(local_file) if local_file.exists() else ""
    if local_hash != entry.get("local_sha256", ""):
        return SyncAction.CONFLICT

    _download()
    return SyncAction.DOWNLOADED


def _ensure_remote_dirs(
    client: ExistClient, full_path: str, source: Path, remote_cols: list[str], dry_run: bool
) -> None:
    """Create remote subcollections that exist locally but not remotely.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        source: Local source directory.
        remote_cols: Relative paths of subcollections already present remotely.
        dry_run: If True, log but do not create.
    """
    remote_col_set = set(remote_cols)
    for local_dir in sorted(p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_dir()):
        if local_dir not in remote_col_set:
            typer.echo(f"+ {local_dir}/  (new collection)")
            if not dry_run:
                client.create_collection(f"{full_path}/{local_dir}")


def _ensure_local_dirs(dest: Path, remote_cols: list[str], dry_run: bool) -> None:
    """Create local subdirectories that exist remotely but not locally.

    Args:
        dest: Local destination directory.
        remote_cols: Relative paths of remote subcollections.
        dry_run: If True, log but do not create.
    """
    for rel_col in remote_cols:
        local_dir = dest / rel_col
        if not local_dir.exists():
            typer.echo(f"+ {rel_col}/  (new directory)")
            if not dry_run:
                local_dir.mkdir(parents=True, exist_ok=True)


def _delete_remote_extras(
    client: ExistClient,
    full_path: str,
    source: Path,
    remote_resources: list[RemoteResource],
    manifest: dict[str, dict],
    dry_run: bool,
) -> int:
    """Delete remote files that have no corresponding local file.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        source: Local source directory.
        remote_resources: All remote resources from the current listing.
        manifest: Sync manifest (mutated in place on deletion).
        dry_run: If True, log but do not delete.

    Returns:
        Number of files deleted (or that would be deleted).
    """
    local_files = {p.relative_to(source).as_posix() for p in source.rglob("*") if p.is_file()}
    count = 0
    for resource in remote_resources:
        if resource.rel_path not in local_files:
            typer.echo(f"✗ {resource.rel_path}  (deleted)")
            if not dry_run:
                client.delete_document(f"{full_path}/{resource.rel_path}")
                manifest.pop(resource.rel_path, None)
            count += 1
    return count


def _delete_local_extras(
    dest: Path,
    remote_resources: list[RemoteResource],
    manifest: dict[str, dict],
    dry_run: bool,
) -> int:
    """Delete local files that have no corresponding remote resource.

    Args:
        dest: Local destination directory.
        remote_resources: All remote resources from the current listing.
        manifest: Sync manifest (mutated in place on deletion).
        dry_run: If True, log but do not delete.

    Returns:
        Number of files deleted (or that would be deleted).
    """
    remote_set = {r.rel_path for r in remote_resources}
    count = 0
    for local_file in sorted(dest.rglob("*")):
        if not local_file.is_file():
            continue
        rel = local_file.relative_to(dest).as_posix()
        if rel not in remote_set:
            typer.echo(f"✗ {rel}  (deleted)")
            if not dry_run:
                local_file.unlink()
                manifest.pop(rel, None)
            count += 1
    return count


def _delete_empty_remote_dirs(
    client: ExistClient,
    full_path: str,
    source: Path,
    dry_run: bool,
) -> int:
    """Delete remote subcollections that are empty and have no local counterpart.

    Re-fetches the remote tree so the check reflects the state after file
    deletions. Processes deepest collections first so parents become empty
    naturally as children are removed.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        source: Local source directory (used to check for local counterparts).
        dry_run: If True, log but do not delete.

    Returns:
        Number of collections deleted (or that would be deleted).
    """
    tree = _walk_remote(client, full_path)
    resource_paths = {r.rel_path for r in tree.resources}
    by_depth = sorted(tree.subcollections, key=lambda c: c.count("/"), reverse=True)
    count = 0
    for rel_col in by_depth:
        if (source / rel_col).is_dir():
            continue
        if any(rp.startswith(f"{rel_col}/") or rp == rel_col for rp in resource_paths):
            continue
        typer.echo(f"✗ {rel_col}/  (empty collection deleted)")
        if not dry_run:
            client.delete_collection(f"{full_path}/{rel_col}")
        count += 1
    return count


def _delete_empty_local_dirs(dest: Path, dry_run: bool) -> int:
    """Delete local subdirectories that are empty after file deletions.

    Processes deepest directories first so parents become empty naturally
    as children are removed.

    Args:
        dest: Local destination directory.
        dry_run: If True, log but do not delete.

    Returns:
        Number of directories deleted (or that would be deleted).
    """
    dirs = [p for p in dest.rglob("*") if p.is_dir()]
    by_depth = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
    count = 0
    for d in by_depth:
        if not any(d.iterdir()):
            rel = d.relative_to(dest).as_posix()
            typer.echo(f"✗ {rel}/  (empty directory deleted)")
            if not dry_run:
                d.rmdir()
            count += 1
    return count


def _print_summary(counts: dict[SyncAction, int]) -> None:
    """Print the sync summary line.

    Args:
        counts: Map of SyncAction to the number of files that took that action.
    """
    parts = []
    for action, label in [
        (SyncAction.UPLOADED, "uploaded"),
        (SyncAction.DOWNLOADED, "downloaded"),
        (SyncAction.SKIPPED, "skipped"),
        (SyncAction.CONFLICT, "conflict"),
        (SyncAction.DELETED, "deleted"),
    ]:
        n = counts.get(action, 0)
        if n:
            parts.append(f"{n} {label}{'s' if n != 1 and label != 'conflict' else ''}")
    typer.echo("---")
    typer.echo(", ".join(parts) if parts else "nothing to do")


def _push(
    source: Path, nick: str, path: str, force: bool, dry_run: bool, delete: bool, checkpoint_every: int
) -> None:
    """Push a local directory tree to a remote collection.

    Args:
        source: Local directory to push from.
        nick: Collection nickname.
        path: Remote path within the collection.
        force: If True, upload all files regardless of manifest state.
        dry_run: If True, print actions without performing them.
        delete: If True, remove remote files absent from the local tree.
        checkpoint_every: Flush the manifest to disk after every N files processed.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path)
    counts: dict[SyncAction, int] = {}

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            tree = _walk_remote(client, full_path)
            remote_index = {r.rel_path: r.entry for r in tree.resources}

            _ensure_remote_dirs(client, full_path, source, tree.subcollections, dry_run)

            local_files = sorted(p for p in source.rglob("*") if p.is_file())
            total = len(local_files)
            for i, local_file in enumerate(local_files, 1):
                rel = local_file.relative_to(source).as_posix()
                remote_mtime = remote_index[rel].last_modified or "" if rel in remote_index else ""
                action = _push_file(client, full_path, local_file, rel, remote_mtime, manifest, force, dry_run)
                pct = int(i / total * 100) if total else 100
                prefix = f"[{pct:3d}%] "
                label = {
                    SyncAction.UPLOADED: f"{prefix}↑ {rel}  ({'new' if rel not in remote_index else 'modified'})",
                    SyncAction.SKIPPED: f"{prefix}= {rel}  (unchanged)",
                    SyncAction.CONFLICT: f"{prefix}! {rel}  (conflict: modified on both sides, skipping)",
                }.get(action, "")
                if label:
                    typer.echo(label)
                counts[action] = counts.get(action, 0) + 1
                if not dry_run and i % checkpoint_every == 0:
                    _save_manifest(nick, path, manifest)

            if delete:
                counts[SyncAction.DELETED] = _delete_remote_extras(
                    client, full_path, source, tree.resources, manifest, dry_run
                )
                counts[SyncAction.DELETED] += _delete_empty_remote_dirs(
                    client, full_path, source, dry_run
                )

            # Re-list to capture server-assigned mtimes after uploads
            if not dry_run and counts.get(SyncAction.UPLOADED, 0):
                updated_tree = _walk_remote(client, full_path)
                for resource in updated_tree.resources:
                    if resource.rel_path in manifest:
                        manifest[resource.rel_path]["remote_last_modified"] = (
                            resource.entry.last_modified or ""
                        )

    if not dry_run:
        _save_manifest(nick, path, manifest)
        invalidate(nick)

    _print_summary(counts)


def _pull(
    nick: str, path: str, dest: Path, force: bool, dry_run: bool, delete: bool, checkpoint_every: int
) -> None:
    """Pull a remote collection into a local directory.

    Args:
        nick: Collection nickname.
        path: Remote path within the collection.
        dest: Local directory to pull into.
        force: If True, download all files regardless of manifest state.
        dry_run: If True, print actions without performing them.
        delete: If True, remove local files absent from the remote collection.
        checkpoint_every: Flush the manifest to disk after every N files processed.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path)
    counts: dict[SyncAction, int] = {}

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            tree = _walk_remote(client, full_path)

            _ensure_local_dirs(dest, tree.subcollections, dry_run)

            total = len(tree.resources)
            for i, resource in enumerate(tree.resources, 1):
                remote_mtime = resource.entry.last_modified or ""
                is_new = resource.rel_path not in manifest
                action = _pull_file(
                    client, full_path, dest, resource.rel_path, remote_mtime, manifest, force, dry_run
                )
                pct = int(i / total * 100) if total else 100
                prefix = f"[{pct:3d}%] "
                label = {
                    SyncAction.DOWNLOADED: f"{prefix}↓ {resource.rel_path}  ({'new' if is_new else 'modified'})",
                    SyncAction.SKIPPED: f"{prefix}= {resource.rel_path}  (unchanged)",
                    SyncAction.CONFLICT: f"{prefix}! {resource.rel_path}  (conflict: modified on both sides, skipping)",
                }.get(action, "")
                if label:
                    typer.echo(label)
                counts[action] = counts.get(action, 0) + 1
                if not dry_run and i % checkpoint_every == 0:
                    _save_manifest(nick, path, manifest)

            if delete:
                counts[SyncAction.DELETED] = _delete_local_extras(
                    dest, tree.resources, manifest, dry_run
                )
                counts[SyncAction.DELETED] += _delete_empty_local_dirs(dest, dry_run)

    if not dry_run:
        _save_manifest(nick, path, manifest)

    _print_summary(counts)


def sync(
    source: str = typer.Argument(
        help="Source: local directory or ``<nick>[:<path>]``.",
        autocompletion=collection_target_completer("collection", allow_local=True),
    ),
    dest: str = typer.Argument(
        help="Destination: local directory or ``<nick>[:<path>]``.",
        autocompletion=collection_target_completer("collection", allow_local=True),
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Transfer all files, bypassing conflict detection."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be transferred without doing it."),
    delete: bool = typer.Option(False, "--delete", help="Remove destination files absent from the source."),
    checkpoint_every: int = typer.Option(
        100, "--checkpoint-every", help="Save the sync manifest every N files so a failed run can resume."
    ),
) -> None:
    """Sync a local folder and a remote collection, transferring only changed files."""
    src_remote = is_remote(source)
    dst_remote = is_remote(dest)

    if src_remote and dst_remote:
        typer.echo("Error: both source and destination are remote. Use cp for remote-to-remote copies.", err=True)
        raise typer.Exit(1)
    if not src_remote and not dst_remote:
        typer.echo("Error: one of source or destination must be a remote collection (nick:path).", err=True)
        raise typer.Exit(1)

    if not src_remote:
        source_path = Path(source)
        if not source_path.is_dir():
            typer.echo(f"Error: '{source}' is not a directory.", err=True)
            raise typer.Exit(1)
        nick, path = parse_target(dest, path_required=False)
        _push(source_path, nick, path, force, dry_run, delete, checkpoint_every)
    else:
        nick, path = parse_target(source, path_required=False)
        _pull(nick, path, Path(dest), force, dry_run, delete, checkpoint_every)
