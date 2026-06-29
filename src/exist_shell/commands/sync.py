"""sync command — sync a local folder with a remote eXist collection."""

import hashlib
import json
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from enum import Enum
from pathlib import Path
from collections.abc import Callable
from typing import NamedTuple, TypedDict

import typer

from exist_shell.cache import invalidate
from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.config import Config
from exist_shell.models import CollectionEntry, ResourceEntry
from exist_shell.utils import (
    check_xml_wellformed,
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


class ManifestEntry(TypedDict, total=False):
    """Per-file state stored in the sync manifest.

    Attributes:
        local_sha256: SHA-256 hex digest of the local file at last sync.
        remote_last_modified: Server-assigned mtime at last sync (empty string
            immediately after upload, before the re-list that records it).
        local_mtime_ns: Local file mtime in nanoseconds at last sync.
        local_size: Local file size in bytes at last sync.
    """

    local_sha256: str
    remote_last_modified: str
    local_mtime_ns: int
    local_size: int


class SyncAction(Enum):
    """Outcome of a single-file sync decision."""

    UPLOADED = "uploaded"
    DOWNLOADED = "downloaded"
    SKIPPED = "skipped"
    CONFLICT = "conflict"
    DELETED = "deleted"
    CREATED = "created"
    INVALID = "invalid"


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


class Manifest:
    """Sync manifest: tracks per-file state and handles checkpoint writes."""

    def __init__(self, data: dict[str, ManifestEntry], checkpoint_every: int) -> None:
        """Initialize the manifest.

        Args:
            data: Per-file state loaded from disk (or empty for a fresh manifest).
            checkpoint_every: Mutation count between automatic checkpoint writes.
        """
        self._data = data
        self._dirty = 0
        self._checkpoint_every = checkpoint_every

    def get(self, rel_path: str) -> ManifestEntry:
        """Return the manifest entry for rel_path, or an empty entry if absent.

        Args:
            rel_path: Relative path of the file within the sync tree.

        Returns:
            The stored ManifestEntry, or an empty ManifestEntry if not present.
        """
        return self._data.get(rel_path, ManifestEntry())

    def __contains__(self, rel_path: str) -> bool:
        """Return True if rel_path has a manifest entry.

        Args:
            rel_path: Relative path of the file within the sync tree.

        Returns:
            True if an entry exists for rel_path, False otherwise.
        """
        return rel_path in self._data

    def set(self, rel_path: str, entry: ManifestEntry) -> None:
        """Upsert an entry and mark the manifest dirty.

        Args:
            rel_path: Relative path of the file within the sync tree.
            entry: New state to store for this file.
        """
        self._data[rel_path] = entry
        self._dirty += 1

    def pop(self, rel_path: str) -> None:
        """Remove an entry (if present) and mark the manifest dirty.

        Args:
            rel_path: Relative path of the file within the sync tree.
        """
        self._data.pop(rel_path, None)
        self._dirty += 1

    def maybe_save(self, nick: str, remote_path: str) -> None:
        """Write to disk when accumulated mutations reach the threshold.

        Args:
            nick: Collection nickname.
            remote_path: Remote collection path.
        """
        if self._dirty >= self._checkpoint_every:
            self._write(nick, remote_path)
            self._dirty = 0

    def save(self, nick: str, remote_path: str) -> None:
        """Unconditional final write.

        Args:
            nick: Collection nickname.
            remote_path: Remote collection path.
        """
        self._write(nick, remote_path)

    def _write(self, nick: str, remote_path: str) -> None:
        """Atomically write manifest data to disk.

        Args:
            nick: Collection nickname.
            remote_path: Remote collection path.
        """
        p = _manifest_path(nick, remote_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data))
        tmp.rename(p)


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


def _load_manifest(nick: str, remote_path: str, checkpoint_every: int) -> Manifest:
    """Load the sync manifest, returning an empty manifest if the file is missing.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.
        checkpoint_every: Mutation count between automatic checkpoint writes.

    Returns:
        Manifest wrapping the last-synced state for each file.
    """
    p = _manifest_path(nick, remote_path)
    if not p.exists():
        return Manifest({}, checkpoint_every)
    try:
        return Manifest(json.loads(p.read_text()), checkpoint_every)
    except Exception:
        return Manifest({}, checkpoint_every)


def _walk_remote(client: ExistClient, base_path: str, max_workers: int = 4) -> RemoteTree:
    """List all resources and subcollections under a remote path.

    Uses a parallel BFS: all subcollections at a given depth are fetched
    concurrently. Results within each level are consumed in submission order
    so that mocked ``side_effect`` sequences in tests remain deterministic.

    Args:
        client: Active ExistClient.
        base_path: Full eXist path to walk (e.g. ``/db/myapp/reports``).
        max_workers: Number of concurrent listing requests.

    Returns:
        RemoteTree with resources and subcollections relative to ``base_path``.
    """
    resources: list[RemoteResource] = []
    subcollections: list[str] = []
    level: list[tuple[str, str]] = [("", base_path)]

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while level:
            futures = [(rel, executor.submit(client.list_collection, full)) for rel, full in level]
            level = []
            try:
                for rel_prefix, future in futures:
                    for item in future.result():
                        if isinstance(item, CollectionEntry):
                            rel_name = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
                            subcollections.append(rel_name)
                            level.append((rel_name, f"{base_path}/{rel_name}"))
                        else:
                            rel_name = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
                            resources.append(RemoteResource(rel_name, item))
            except KeyboardInterrupt:
                executor.shutdown(wait=False, cancel_futures=True)
                raise

    return RemoteTree(resources, subcollections)


def _push_file_task(
    client: ExistClient,
    full_path: str,
    local_file: Path,
    rel_path: str,
    remote_mtime: str,
    entry: ManifestEntry,
    in_manifest: bool,
    force: bool,
    dry_run: bool,
) -> tuple[SyncAction, ManifestEntry | None]:
    """Decide and execute the push action for a single file.

    Reads the local file at most once regardless of which code path is taken.
    Returns the action and the manifest entry to store; the caller applies the
    update. Never mutates the manifest directly.

    Stores an empty ``remote_last_modified`` after upload; callers must re-list
    the remote collection afterwards to record the server-assigned mtime.

    Uses a stat-based fast path: if both the local file's mtime/size and the
    remote mtime match the manifest, the file is skipped without reading or
    hashing its contents.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection (e.g. ``/db/myapp``).
        local_file: Local file to upload.
        rel_path: Relative path of the file within the sync tree.
        remote_mtime: Current ``last_modified`` from the remote listing.
        entry: Manifest entry for this file (empty dict if not previously synced).
        in_manifest: True if this file has an existing manifest entry.
        force: If True, upload regardless of manifest state.
        dry_run: If True, do not perform the upload.

    Returns:
        Tuple of (action, new_manifest_entry). new_manifest_entry is None when
        no manifest update is warranted.
    """
    mime = guess_mime(local_file, "application/xml")

    if force or not in_manifest:
        data = local_file.read_bytes()
        if check_xml_wellformed(data, mime):
            return SyncAction.INVALID, None
        stat = local_file.stat()
        local_hash = hashlib.sha256(data).hexdigest()
        if not dry_run:
            client.put_document(f"{full_path}/{rel_path}", data, mime)
        return SyncAction.UPLOADED, ManifestEntry(
            local_sha256=local_hash,
            remote_last_modified="",
            local_mtime_ns=stat.st_mtime_ns,
            local_size=stat.st_size,
        )

    remote_changed = remote_mtime != entry.get("remote_last_modified", "")
    stat = local_file.stat()
    stat_changed = (
        stat.st_mtime_ns != entry.get("local_mtime_ns", -1)
        or stat.st_size != entry.get("local_size", -1)
    )

    if not stat_changed and not remote_changed:
        return SyncAction.SKIPPED, None

    data = local_file.read_bytes()
    local_hash = hashlib.sha256(data).hexdigest()
    local_changed = local_hash != entry.get("local_sha256", "")

    if local_changed and remote_changed:
        return SyncAction.CONFLICT, None

    if local_changed:
        if check_xml_wellformed(data, mime):
            return SyncAction.INVALID, None
        if not dry_run:
            client.put_document(f"{full_path}/{rel_path}", data, mime)
        return SyncAction.UPLOADED, ManifestEntry(
            local_sha256=local_hash,
            remote_last_modified="",
            local_mtime_ns=stat.st_mtime_ns,
            local_size=stat.st_size,
        )

    # stat changed but content identical (e.g. file was touched) — refresh stat only
    return SyncAction.SKIPPED, ManifestEntry(
        **{**entry, "local_mtime_ns": stat.st_mtime_ns, "local_size": stat.st_size}
    )


def _pull_file_task(
    client: ExistClient,
    full_path: str,
    dest: Path,
    rel_path: str,
    remote_mtime: str,
    entry: ManifestEntry,
    in_manifest: bool,
    force: bool,
    dry_run: bool,
) -> tuple[SyncAction, ManifestEntry | None]:
    """Decide and execute the pull action for a single file.

    Returns the action and the manifest entry to store; the caller applies the
    update. Never mutates the manifest directly.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection (e.g. ``/db/myapp``).
        dest: Local directory to pull into.
        rel_path: Relative path of the file within the sync tree.
        remote_mtime: Current ``last_modified`` from the remote listing.
        entry: Manifest entry for this file (empty dict if not previously synced).
        in_manifest: True if this file has an existing manifest entry.
        force: If True, download regardless of manifest state.
        dry_run: If True, do not perform the download.

    Returns:
        Tuple of (action, new_manifest_entry). new_manifest_entry is None when
        dry_run is True or no manifest update is warranted.
    """
    local_file = dest / rel_path

    def _download() -> ManifestEntry | None:
        if dry_run:
            return None
        result = client.get_document(f"{full_path}/{rel_path}")
        local_file.parent.mkdir(parents=True, exist_ok=True)
        local_file.write_bytes(result.content)
        stat = local_file.stat()
        return ManifestEntry(
            local_sha256=_sha256(local_file),
            remote_last_modified=remote_mtime,
            local_mtime_ns=stat.st_mtime_ns,
            local_size=stat.st_size,
        )

    if force or not in_manifest:
        return SyncAction.DOWNLOADED, _download()

    remote_changed = remote_mtime != entry.get("remote_last_modified", "")

    if not remote_changed:
        if not local_file.exists():
            return SyncAction.DOWNLOADED, _download()
        return SyncAction.SKIPPED, None

    local_hash = _sha256(local_file) if local_file.exists() else ""
    if local_hash != entry.get("local_sha256", ""):
        return SyncAction.CONFLICT, None

    return SyncAction.DOWNLOADED, _download()


def _ensure_remote_dirs(
    client: ExistClient, full_path: str, local_dirs: set[str], remote_cols: list[str], dry_run: bool
) -> None:
    """Create remote subcollections that exist locally but not remotely.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        local_dirs: Relative paths of all local subdirectories.
        remote_cols: Relative paths of subcollections already present remotely.
        dry_run: If True, log but do not create.
    """
    remote_col_set = set(remote_cols)
    for local_dir in sorted(local_dirs):
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
    local_files: set[str],
    remote_resources: list[RemoteResource],
    manifest: Manifest,
    dry_run: bool,
) -> int:
    """Delete remote files that have no corresponding local file.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        local_files: Relative paths of all local files.
        remote_resources: All remote resources from the current listing.
        manifest: Sync manifest (mutated in place on deletion).
        dry_run: If True, log but do not delete.

    Returns:
        Number of files deleted (or that would be deleted).
    """
    count = 0
    for resource in remote_resources:
        if resource.rel_path not in local_files:
            typer.echo(f"✗ {resource.rel_path}  (deleted)")
            if not dry_run:
                client.delete_document(f"{full_path}/{resource.rel_path}")
                manifest.pop(resource.rel_path)
            count += 1
    return count


def _delete_local_extras(
    dest: Path,
    remote_resources: list[RemoteResource],
    manifest: Manifest,
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
        rel_path = local_file.relative_to(dest).as_posix()
        if rel_path not in remote_set:
            typer.echo(f"✗ {rel_path}  (deleted)")
            if not dry_run:
                local_file.unlink()
                manifest.pop(rel_path)
            count += 1
    return count


def _delete_empty_remote_dirs(
    client: ExistClient,
    full_path: str,
    source: Path,
    dry_run: bool,
    max_workers: int = 4,
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
        max_workers: Number of concurrent listing requests for the re-walk.

    Returns:
        Number of collections deleted (or that would be deleted).
    """
    tree = _walk_remote(client, full_path, max_workers=max_workers)
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
    no_plural = {"conflict", "invalid xml"}
    for action, label in [
        (SyncAction.UPLOADED, "uploaded"),
        (SyncAction.DOWNLOADED, "downloaded"),
        (SyncAction.SKIPPED, "skipped"),
        (SyncAction.CONFLICT, "conflict"),
        (SyncAction.DELETED, "deleted"),
        (SyncAction.INVALID, "invalid xml"),
    ]:
        n = counts.get(action, 0)
        if n:
            parts.append(f"{n} {label}{'s' if n != 1 and label not in no_plural else ''}")
    typer.echo("---")
    typer.echo(", ".join(parts) if parts else "nothing to do")


def _push_label(
    action: SyncAction,
    rel_path: str,
    pct: int,
    remote_index: dict[str, ResourceEntry],
    verbose: bool,
) -> str:
    """Format the progress line for a push action, or return empty string to suppress output.

    Args:
        action: The sync action taken.
        rel_path: Relative path of the file.
        pct: Completion percentage (0–100).
        remote_index: Map of remote rel_path → ResourceEntry, used to classify new vs modified.
        verbose: If True, include SKIPPED lines.

    Returns:
        Formatted progress string, or empty string if the action should not be printed.
    """
    prefix = f"[{pct:3d}%] "
    labels: dict[SyncAction, str] = {
        SyncAction.UPLOADED: f"{prefix}↑ {rel_path}  ({'new' if rel_path not in remote_index else 'modified'})",
        SyncAction.CONFLICT: f"{prefix}! {rel_path}  (conflict: modified on both sides, skipping)",
        SyncAction.INVALID: f"{prefix}! {rel_path}  (not well-formed XML, skipping)",
    }
    if verbose:
        labels[SyncAction.SKIPPED] = f"{prefix}= {rel_path}  (unchanged)"
    return labels.get(action, "")


def _pull_label(
    action: SyncAction,
    rel_path: str,
    pct: int,
    is_new: bool,
    verbose: bool,
) -> str:
    """Format the progress line for a pull action, or return empty string to suppress output.

    Args:
        action: The sync action taken.
        rel_path: Relative path of the file.
        pct: Completion percentage (0–100).
        is_new: True if the file was not previously in the manifest.
        verbose: If True, include SKIPPED lines.

    Returns:
        Formatted progress string, or empty string if the action should not be printed.
    """
    prefix = f"[{pct:3d}%] "
    labels: dict[SyncAction, str] = {
        SyncAction.DOWNLOADED: f"{prefix}↓ {rel_path}  ({'new' if is_new else 'modified'})",
        SyncAction.CONFLICT: f"{prefix}! {rel_path}  (conflict: modified on both sides, skipping)",
    }
    if verbose:
        labels[SyncAction.SKIPPED] = f"{prefix}= {rel_path}  (unchanged)"
    return labels.get(action, "")


def _run_push_sequential(
    client: ExistClient,
    full_path: str,
    local_files: list[Path],
    source: Path,
    remote_index: dict[str, ResourceEntry],
    manifest: Manifest,
    force: bool,
    dry_run: bool,
    verbose: bool,
    nick: str,
    path: str,
) -> tuple[dict[SyncAction, int], bool]:
    """Run the push file loop sequentially, stopping on the first failure.

    Used when ``--fail-fast`` is active to guarantee that no file after the
    first conflict or invalid XML is ever transferred.

    Args:
        client: Active ExistClient.
        full_path: Full eXist collection path.
        local_files: Sorted list of local files to process.
        source: Local root directory (used to compute relative paths).
        remote_index: Map of remote rel_path → ResourceEntry.
        manifest: Sync manifest (mutated in place as files are processed).
        force: If True, upload regardless of manifest state.
        dry_run: If True, print actions without uploading.
        verbose: If True, print unchanged files.
        nick: Collection nickname (for manifest checkpoints).
        path: Remote collection path (for manifest checkpoints).

    Returns:
        Tuple of (counts, fail_fast_triggered).
    """
    counts: dict[SyncAction, int] = {}
    total = len(local_files)
    for i, local_file in enumerate(local_files, 1):
        rel_path = local_file.relative_to(source).as_posix()
        remote_mtime = remote_index[rel_path].last_modified or "" if rel_path in remote_index else ""
        action, new_entry = _push_file_task(
            client, full_path, local_file, rel_path, remote_mtime,
            manifest.get(rel_path), rel_path in manifest, force, dry_run,
        )
        pct = int(i / total * 100) if total else 100
        label = _push_label(action, rel_path, pct, remote_index, verbose)
        if label:
            typer.echo(label)
        counts[action] = counts.get(action, 0) + 1
        if not dry_run and new_entry is not None:
            manifest.set(rel_path, new_entry)
        manifest.maybe_save(nick, path)
        if action in {SyncAction.INVALID, SyncAction.CONFLICT}:
            return counts, True
    return counts, False


def _drain_futures(
    executor: ThreadPoolExecutor,
    futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int], str]]],
    manifest: Manifest,
    nick: str,
    path: str,
    total: int,
    dry_run: bool,
) -> dict[SyncAction, int]:
    """Drain a futures dict produced by a parallel sync loop.

    Iterates completed futures in arrival order, prints progress labels, updates
    action counts and the manifest, and handles KeyboardInterrupt cleanly.

    Args:
        executor: The active ThreadPoolExecutor owning the futures.
        futures: Map of future → (rel_path, label_fn) where label_fn(action, pct) → str.
        manifest: Sync manifest (mutated in place as futures complete).
        nick: Collection nickname (for manifest checkpoints).
        path: Remote collection path (for manifest checkpoints).
        total: Total number of tasks, used to compute the completion percentage.
        dry_run: If True, skip manifest writes.

    Returns:
        Action counts keyed by SyncAction.
    """
    counts: dict[SyncAction, int] = {}
    completed = 0
    try:
        for future in as_completed(futures):
            rel_path, label_fn = futures[future]
            action, new_entry = future.result()
            completed += 1
            pct = int(completed / total * 100) if total else 100
            label = label_fn(action, pct)
            if label:
                typer.echo(label)
            counts[action] = counts.get(action, 0) + 1
            if not dry_run and new_entry is not None:
                manifest.set(rel_path, new_entry)
            manifest.maybe_save(nick, path)
    except KeyboardInterrupt:
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    return counts


def _run_push_parallel(
    client: ExistClient,
    full_path: str,
    local_files: list[Path],
    source: Path,
    remote_index: dict[str, ResourceEntry],
    manifest: Manifest,
    force: bool,
    dry_run: bool,
    verbose: bool,
    nick: str,
    path: str,
    jobs: int,
) -> dict[SyncAction, int]:
    """Run the push file loop with concurrent uploads.

    All files are submitted to the thread pool upfront. Manifest mutations and
    progress output happen only in the main thread as each future completes,
    so no locking is required.

    Args:
        client: Active ExistClient.
        full_path: Full eXist collection path.
        local_files: Sorted list of local files to process.
        source: Local root directory (used to compute relative paths).
        remote_index: Map of remote rel_path → ResourceEntry.
        manifest: Sync manifest (mutated in place as files are processed).
        force: If True, upload regardless of manifest state.
        dry_run: If True, print actions without uploading.
        verbose: If True, print unchanged files.
        nick: Collection nickname (for manifest checkpoints).
        path: Remote collection path (for manifest checkpoints).
        jobs: Number of parallel upload workers.

    Returns:
        Action counts.
    """
    total = len(local_files)
    tasks = [(lf, lf.relative_to(source).as_posix()) for lf in local_files]
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int], str]]] = {
            executor.submit(
                _push_file_task,
                client, full_path, lf, rp,
                remote_index[rp].last_modified or "" if rp in remote_index else "",
                manifest.get(rp), rp in manifest, force, dry_run,
            ): (rp, lambda a, p, _rp=rp: _push_label(a, _rp, p, remote_index, verbose))
            for lf, rp in tasks
        }
        return _drain_futures(executor, futures, manifest, nick, path, total, dry_run)


def _refresh_remote_mtimes(
    client: ExistClient, full_path: str, manifest: Manifest, jobs: int
) -> None:
    """Re-list the remote collection and record server-assigned mtimes in the manifest.

    Called after uploads because eXist assigns the mtime at write time; we
    cannot know it until we re-fetch the collection listing.

    Args:
        client: Active ExistClient.
        full_path: Full eXist collection path.
        manifest: Manifest to update in place.
        jobs: Parallel workers for the re-walk.
    """
    updated_tree = _walk_remote(client, full_path, max_workers=jobs)
    for resource in updated_tree.resources:
        if resource.rel_path in manifest:
            manifest.get(resource.rel_path)["remote_last_modified"] = (
                resource.entry.last_modified or ""
            )


def _run_pull_parallel(
    client: ExistClient,
    full_path: str,
    dest: Path,
    resources: list[RemoteResource],
    manifest: Manifest,
    force: bool,
    dry_run: bool,
    verbose: bool,
    nick: str,
    path: str,
    jobs: int,
) -> dict[SyncAction, int]:
    """Run the pull file loop with concurrent downloads.

    All files are submitted to the thread pool upfront. Manifest mutations and
    progress output happen only in the main thread as each future completes,
    so no locking is required.

    Args:
        client: Active ExistClient.
        full_path: Full eXist collection path.
        dest: Local directory to pull into.
        resources: Remote resources to download.
        manifest: Sync manifest (mutated in place as files are processed).
        force: If True, download regardless of manifest state.
        dry_run: If True, print actions without downloading.
        verbose: If True, print unchanged files.
        nick: Collection nickname (for manifest checkpoints).
        path: Remote collection path (for manifest checkpoints).
        jobs: Number of parallel download workers.

    Returns:
        Action counts.
    """
    total = len(resources)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int], str]]] = {
            executor.submit(
                _pull_file_task,
                client, full_path, dest, resource.rel_path, resource.entry.last_modified or "",
                manifest.get(resource.rel_path), resource.rel_path in manifest, force, dry_run,
            ): (
                resource.rel_path,
                lambda a, p, _rp=resource.rel_path, _new=(resource.rel_path not in manifest): _pull_label(a, _rp, p, _new, verbose),
            )
            for resource in resources
        }
        return _drain_futures(executor, futures, manifest, nick, path, total, dry_run)


def _push(
    source: Path,
    nick: str,
    path: str,
    force: bool,
    fail_fast: bool,
    dry_run: bool,
    delete: bool,
    checkpoint_every: int,
    verbose: bool,
    jobs: int,
) -> None:
    """Push a local directory tree to a remote collection.

    Args:
        source: Local directory to push from.
        nick: Collection nickname.
        path: Remote path within the collection.
        force: If True, upload all files regardless of manifest state.
        fail_fast: If True, stop on the first conflict or XML validation failure
            (manifest is saved). Runs sequentially to guarantee no file after
            the first failure is transferred.
        dry_run: If True, print actions without performing them.
        delete: If True, remove remote files absent from the local tree.
        checkpoint_every: Save the manifest after every N mutations.
        verbose: If True, also print unchanged (skipped) files.
        jobs: Number of parallel upload workers.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path, checkpoint_every)
    counts: dict[SyncAction, int] = {}
    fail_fast_triggered = False

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                tree = _walk_remote(client, full_path, max_workers=jobs)
                remote_index = {r.rel_path: r.entry for r in tree.resources}

                all_paths = list(source.rglob("*"))
                local_files = sorted(p for p in all_paths if p.is_file())
                local_dirs = {p.relative_to(source).as_posix() for p in all_paths if p.is_dir()}
                local_file_rels = {p.relative_to(source).as_posix() for p in local_files}

                _ensure_remote_dirs(client, full_path, local_dirs, tree.subcollections, dry_run)

                if fail_fast:
                    counts, fail_fast_triggered = _run_push_sequential(
                        client, full_path, local_files, source, remote_index,
                        manifest, force, dry_run, verbose, nick, path,
                    )
                else:
                    counts = _run_push_parallel(
                        client, full_path, local_files, source, remote_index,
                        manifest, force, dry_run, verbose, nick, path, jobs,
                    )

                if not fail_fast_triggered and delete:
                    deleted = _delete_remote_extras(
                        client, full_path, local_file_rels, tree.resources, manifest, dry_run
                    )
                    deleted += _delete_empty_remote_dirs(
                        client, full_path, source, dry_run, max_workers=jobs
                    )
                    counts[SyncAction.DELETED] = deleted

                if not dry_run and counts.get(SyncAction.UPLOADED, 0):
                    _refresh_remote_mtimes(client, full_path, manifest, jobs)
    except KeyboardInterrupt:
        if not dry_run:
            manifest.save(nick, path)
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)

    if not dry_run:
        manifest.save(nick, path)
        invalidate(nick)

    _print_summary(counts)

    if fail_fast_triggered:
        raise typer.Exit(1)


def _pull(
    nick: str,
    path: str,
    dest: Path,
    force: bool,
    dry_run: bool,
    delete: bool,
    checkpoint_every: int,
    verbose: bool,
    jobs: int,
) -> None:
    """Pull a remote collection into a local directory.

    Args:
        nick: Collection nickname.
        path: Remote path within the collection.
        dest: Local directory to pull into.
        force: If True, download all files regardless of manifest state.
        dry_run: If True, print actions without performing them.
        delete: If True, remove local files absent from the remote collection.
        checkpoint_every: Save the manifest after every N mutations.
        verbose: If True, also print unchanged (skipped) files.
        jobs: Number of parallel download workers.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path, checkpoint_every)
    counts: dict[SyncAction, int] = {}

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                tree = _walk_remote(client, full_path, max_workers=jobs)
                _ensure_local_dirs(dest, tree.subcollections, dry_run)

                counts = _run_pull_parallel(
                    client, full_path, dest, tree.resources,
                    manifest, force, dry_run, verbose, nick, path, jobs,
                )

                if delete:
                    deleted = _delete_local_extras(dest, tree.resources, manifest, dry_run)
                    deleted += _delete_empty_local_dirs(dest, dry_run)
                    counts[SyncAction.DELETED] = counts.get(SyncAction.DELETED, 0) + deleted
    except KeyboardInterrupt:
        if not dry_run:
            manifest.save(nick, path)
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)

    if not dry_run:
        manifest.save(nick, path)

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
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop on the first conflict or XML validation failure (manifest is saved so the run can resume)."),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be transferred without doing it."),
    delete: bool = typer.Option(False, "--delete", help="Remove destination files absent from the source."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show unchanged (skipped) files in addition to transfers."),
    jobs: int = typer.Option(4, "--jobs", "-j", help="Number of parallel transfer workers."),
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
        _push(source_path, nick, path, force, fail_fast, dry_run, delete, checkpoint_every, verbose, jobs)
    else:
        nick, path = parse_target(source, path_required=False)
        _pull(nick, path, Path(dest), force, dry_run, delete, checkpoint_every, verbose, jobs)
