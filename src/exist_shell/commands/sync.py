"""sync command — sync a local folder with a remote eXist collection."""

import fnmatch
import hashlib
import json
import sys
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
from exist_shell.exceptions import ExistError, ExistNotFoundError
from exist_shell.models import CollectionEntry, ResourceEntry
from exist_shell.utils import (
    check_xml_wellformed,
    echo_tty,
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
    FAILED = "failed"


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
        failed: Relative paths of subcollections whose listing failed.
    """

    resources: list[RemoteResource]
    subcollections: list[str]
    failed: list[str]


class Manifest:
    """Sync manifest: tracks per-file state, exclude patterns, and checkpoint writes."""

    def __init__(
        self,
        data: dict[str, ManifestEntry],
        checkpoint_every: int,
        path: Path,
        excludes: list[str],
    ) -> None:
        """Initialize the manifest.

        Args:
            data: Per-file state loaded from disk (or empty for a fresh manifest).
            checkpoint_every: Mutation count between automatic checkpoint writes.
            path: File path this manifest is persisted to.
            excludes: Exclude patterns persisted alongside the file entries.
        """
        self._data = data
        self._dirty = 0
        self._checkpoint_every = checkpoint_every
        self._path = path
        self.excludes = excludes

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

    def rel_paths(self) -> list[str]:
        """Return the relative paths of all tracked files.

        Returns:
            List of rel_paths with a manifest entry, safe to iterate while
            mutating the manifest.
        """
        return list(self._data)

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

    def maybe_save(self) -> None:
        """Write to disk when accumulated mutations reach the threshold."""
        if self._dirty >= self._checkpoint_every:
            self._write()
            self._dirty = 0

    def save(self) -> None:
        """Unconditional final write."""
        self._write()

    def _write(self) -> None:
        """Atomically write manifest data to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"excludes": self.excludes, "entries": self._data}))
        tmp.rename(self._path)


def _sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's contents.

    Args:
        path: Local file to hash.

    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_excluded(rel_path: str, patterns: list[str]) -> bool:
    """Return True if a relative path matches any exclude pattern.

    Patterns use ``fnmatch`` syntax (``*``, ``?``, ``[seq]``). A pattern
    containing ``/`` is matched against the full relative path and each of
    its ancestor prefixes, so a directory match excludes everything below
    it. A pattern without ``/`` is matched against every individual path
    segment, excluding the path at any depth.

    Args:
        rel_path: POSIX-style path relative to the sync root.
        patterns: Exclude patterns to test against.

    Returns:
        True if the path is excluded by at least one pattern.
    """
    segments = rel_path.split("/")
    prefixes = ["/".join(segments[: i + 1]) for i in range(len(segments))]
    for pattern in patterns:
        if "/" in pattern:
            if any(fnmatch.fnmatchcase(prefix, pattern) for prefix in prefixes):
                return True
        elif any(fnmatch.fnmatchcase(segment, pattern) for segment in segments):
            return True
    return False


def _manifest_path(nick: str, remote_path: str, local_dir: Path) -> Path:
    """Return the manifest file path for a (nick, remote_path, local_dir) triple.

    The local directory is included in the key so that two working copies of
    the same remote collection get independent manifests instead of silently
    corrupting each other's sync state.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.
        local_dir: Local sync directory (source for push, destination for pull).

    Returns:
        Absolute path to the JSON manifest file.
    """
    key_input = f"{remote_path}\x00{local_dir.resolve()}"
    key = hashlib.sha256(key_input.encode()).hexdigest()[:16]
    return _get_sync_cache_dir() / f"{nick}@{key}.json"


def _load_manifest(nick: str, remote_path: str, local_dir: Path, checkpoint_every: int) -> Manifest:
    """Load the sync manifest, returning an empty manifest if the file is missing.

    Reads both manifest formats: the current wrapper format
    ``{"excludes": [...], "entries": {rel_path: entry}}`` and the legacy flat
    ``{rel_path: entry}`` format, which is loaded with an empty exclude list.

    Args:
        nick: Collection nickname.
        remote_path: Remote collection path.
        local_dir: Local sync directory (source for push, destination for pull).
        checkpoint_every: Mutation count between automatic checkpoint writes.

    Returns:
        Manifest wrapping the last-synced state for each file.
    """
    p = _manifest_path(nick, remote_path, local_dir)
    if not p.exists():
        return Manifest({}, checkpoint_every, p, [])
    try:
        raw = json.loads(p.read_text())
        if "entries" in raw:
            return Manifest(raw["entries"], checkpoint_every, p, raw.get("excludes", []))
        return Manifest(raw, checkpoint_every, p, [])
    except Exception:
        return Manifest({}, checkpoint_every, p, [])


def _resolve_excludes(manifest: Manifest, exclude: list[str], clear_exclude: bool) -> list[str]:
    """Resolve the effective exclude patterns for this run.

    Starts from the list stored in the manifest (emptied first when
    ``clear_exclude`` is set) and merges in any newly passed patterns
    (set union). The merged list is stored back on ``manifest.excludes``,
    so the next manifest save persists it; dry runs never save, so their
    merges and clears are honored for the run but not persisted.

    When the merge adds new patterns to a non-empty stored list, a short
    heads-up naming the resulting set is printed on interactive (TTY) runs,
    so the merge isn't a silent surprise. Piped/scripted runs stay silent.

    Args:
        manifest: Loaded sync manifest for this pair.
        exclude: Patterns passed via ``--exclude`` (possibly empty).
        clear_exclude: If True, discard the stored list before merging.

    Returns:
        The effective exclude pattern list for this run, sorted.
    """
    stored = [] if clear_exclude else manifest.excludes
    new = set(exclude) - set(stored)
    merged = sorted(set(stored) | set(exclude))
    if stored and new:
        plural = "s" if len(new) != 1 else ""
        echo_tty(
            f"Merging {len(new)} new exclude pattern{plural} into stored list (now: {', '.join(merged)})."
        )
    manifest.excludes = merged
    return merged


def _walk_remote(client: ExistClient, base_path: str, max_workers: int = 4) -> RemoteTree:
    """List all resources and subcollections under a remote path.

    Uses a parallel BFS: all subcollections at a given depth are fetched
    concurrently. Results within each level are consumed in submission order
    so that mocked ``side_effect`` sequences in tests remain deterministic.

    A failure listing the root path itself propagates immediately, since
    there is nothing to walk without it. A failure listing a subcollection
    discovered deeper in the tree is reported and skipped so the rest of the
    walk can continue.

    Args:
        client: Active ExistClient.
        base_path: Full eXist path to walk (e.g. ``/db/myapp/reports``).
        max_workers: Number of concurrent listing requests.

    Returns:
        RemoteTree with resources and subcollections relative to ``base_path``,
        plus the relative paths of any subcollections whose listing failed.
    """
    resources: list[RemoteResource] = []
    subcollections: list[str] = []
    failed: list[str] = []
    level: list[tuple[str, str]] = [("", base_path)]
    root_level = True

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while level:
            futures = [(rel, executor.submit(client.list_collection, full)) for rel, full in level]
            level = []
            try:
                for rel_prefix, future in futures:
                    if root_level:
                        items = future.result()
                    else:
                        try:
                            items = future.result()
                        except Exception as exc:
                            typer.echo(f"! {rel_prefix}  (error: {exc})", err=True)
                            failed.append(rel_prefix)
                            continue
                    for item in items:
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
            root_level = False

    return RemoteTree(resources, subcollections, failed)


def _filter_tree(tree: RemoteTree, excludes: list[str]) -> RemoteTree:
    """Return a copy of a remote tree with excluded paths removed.

    Filters both resources and subcollections, so everything below an
    excluded directory disappears from the tree along with the directory
    itself. Failed subcollections are kept as-is.

    Args:
        tree: The remote tree to filter.
        excludes: Exclude patterns to apply.

    Returns:
        A RemoteTree without the excluded resources and subcollections.
    """
    if not excludes:
        return tree
    return RemoteTree(
        [r for r in tree.resources if not _is_excluded(r.rel_path, excludes)],
        [c for c in tree.subcollections if not _is_excluded(c, excludes)],
        tree.failed,
    )


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
    excludes: list[str],
    dry_run: bool,
) -> int:
    """Delete local files that have no corresponding remote resource.

    Excluded paths are never treated as extras: the remote listing is
    already filtered, so without this skip every excluded local file
    would look like it has no remote counterpart and be deleted.

    Args:
        dest: Local destination directory.
        remote_resources: Remote resources from the current (filtered) listing.
        manifest: Sync manifest (mutated in place on deletion).
        excludes: Exclude patterns; matching local files are left alone.
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
        if _is_excluded(rel_path, excludes):
            continue
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
    excludes: list[str],
    dry_run: bool,
    max_workers: int = 4,
) -> int:
    """Delete remote subcollections that are empty and have no local counterpart.

    Re-fetches the remote tree so the check reflects the state after file
    deletions. Processes deepest collections first so parents become empty
    naturally as children are removed. Excluded collections are never
    deletion candidates, but the emptiness check uses the unfiltered
    re-walk, so a collection holding only excluded resources is not
    considered empty.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        source: Local source directory (used to check for local counterparts).
        excludes: Exclude patterns; matching collections are left alone.
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
        if _is_excluded(rel_col, excludes):
            continue
        if (source / rel_col).is_dir():
            continue
        if any(rp.startswith(f"{rel_col}/") or rp == rel_col for rp in resource_paths):
            continue
        typer.echo(f"✗ {rel_col}/  (empty collection deleted)")
        if not dry_run:
            client.delete_collection(f"{full_path}/{rel_col}")
        count += 1
    return count


def _delete_empty_local_dirs(dest: Path, excludes: list[str], dry_run: bool) -> int:
    """Delete local subdirectories that are empty after file deletions.

    Processes deepest directories first so parents become empty naturally
    as children are removed. Excluded directories are never deleted, even
    when empty.

    Args:
        dest: Local destination directory.
        excludes: Exclude patterns; matching directories are left alone.
        dry_run: If True, log but do not delete.

    Returns:
        Number of directories deleted (or that would be deleted).
    """
    dirs = [p for p in dest.rglob("*") if p.is_dir()]
    by_depth = sorted(dirs, key=lambda p: len(p.parts), reverse=True)
    count = 0
    for d in by_depth:
        if _is_excluded(d.relative_to(dest).as_posix(), excludes):
            continue
        if not any(d.iterdir()):
            rel = d.relative_to(dest).as_posix()
            typer.echo(f"✗ {rel}/  (empty directory deleted)")
            if not dry_run:
                d.rmdir()
            count += 1
    return count


def _cleanup_newly_excluded(
    client: ExistClient,
    full_path: str,
    local_root: Path,
    manifest: Manifest,
    excludes: list[str],
    yes: bool,
    keep_excluded: bool,
    dry_run: bool,
) -> int:
    """Handle previously synced files that are now covered by exclude patterns.

    A file with a manifest entry was synced through this pair before; once it
    becomes excluded, its copies are deleted on both sides (local and remote)
    so excluding a folder retires it everywhere, not just from tracking.
    Deletion is confirmed interactively unless ``yes`` is set; declining (or
    running without a TTY and without ``yes``) keeps the files, and
    ``keep_excluded`` does the same without prompting. In every case the
    stale manifest entries are dropped, making this a one-time cleanup:
    excluded paths recreated later are left alone.

    After deleting files, excluded ancestor directories that ended up empty
    are removed as well — locally via ``rmdir`` and remotely only after an
    explicit emptiness check, so never-synced content inside an excluded
    directory always survives.

    Args:
        client: Active ExistClient.
        full_path: Full eXist base path of the collection.
        local_root: Local side of the sync (source for push, dest for pull).
        manifest: Sync manifest (mutated in place).
        excludes: Effective exclude patterns for this run.
        yes: If True, skip the confirmation prompt.
        keep_excluded: If True, keep the files and only drop tracking.
        dry_run: If True, report what would be deleted without doing it.

    Returns:
        Number of files deleted (or that would be deleted on a dry run).
    """
    stale = sorted(rp for rp in manifest.rel_paths() if _is_excluded(rp, excludes))
    if not stale:
        return 0

    if keep_excluded:
        # Dropped entries are only persisted by a later manifest save, which
        # dry runs never do — so no dry_run guard is needed here.
        for rel_path in stale:
            manifest.pop(rel_path)
        typer.echo(f"Untracked {len(stale)} excluded file(s), kept in place.")
        return 0

    if dry_run:
        for rel_path in stale:
            typer.echo(f"✗ {rel_path}  (excluded, would delete)")
        return len(stale)

    if yes:
        confirmed = True
    elif sys.stdin.isatty():
        confirmed = typer.confirm(
            f"Delete {len(stale)} previously-synced file(s) matching excluded patterns (local and remote)?"
        )
    else:
        # Non-interactive run without --yes: never delete silently.
        typer.echo(
            "Skipping deletion of newly excluded file(s) (no TTY; use --yes to delete or --keep-excluded to silence this).",
            err=True,
        )
        confirmed = False

    # Entries are dropped even when deletion was declined: the files stay,
    # but they are excluded now, so they must stop being tracked.
    for rel_path in stale:
        manifest.pop(rel_path)

    if not confirmed:
        return 0

    for rel_path in stale:
        (local_root / rel_path).unlink(missing_ok=True)
        try:
            client.delete_document(f"{full_path}/{rel_path}")
        except ExistNotFoundError:
            pass  # already gone remotely — deletion is idempotent
        typer.echo(f"✗ {rel_path}  (excluded, deleted)")

    # The deleted files may leave empty directories behind. Only ancestor
    # directories that are themselves excluded are candidates for removal:
    # a non-excluded parent may legitimately hold other synced content.
    excluded_dirs = set()
    for rel_path in stale:
        parts = rel_path.split("/")[:-1]
        for i in range(1, len(parts) + 1):
            prefix = "/".join(parts[:i])
            if _is_excluded(prefix, excludes):
                excluded_dirs.add(prefix)

    # Deepest first, so a parent becomes empty once its children are gone.
    # Both removals are strictly empty-only: never-synced files inside an
    # excluded directory must survive. Remotely that requires an explicit
    # listing check, because delete_collection deletes recursively.
    for rel_col in sorted(excluded_dirs, key=lambda c: c.count("/"), reverse=True):
        local_dir = local_root / rel_col
        if local_dir.is_dir() and not any(local_dir.iterdir()):
            local_dir.rmdir()
        try:
            if not client.list_collection(f"{full_path}/{rel_col}"):
                client.delete_collection(f"{full_path}/{rel_col}")
        except ExistError:
            pass  # best-effort: a leftover empty collection is harmless

    return len(stale)


def _print_summary(counts: dict[SyncAction, int]) -> None:
    """Print the sync summary line.

    Args:
        counts: Map of SyncAction to the number of files that took that action.
    """
    parts = []
    no_plural = {"conflict", "invalid xml", "failed"}
    for action, label in [
        (SyncAction.UPLOADED, "uploaded"),
        (SyncAction.DOWNLOADED, "downloaded"),
        (SyncAction.SKIPPED, "skipped"),
        (SyncAction.CONFLICT, "conflict"),
        (SyncAction.DELETED, "deleted"),
        (SyncAction.INVALID, "invalid xml"),
        (SyncAction.FAILED, "failed"),
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
    error: str = "",
) -> str:
    """Format the progress line for a push action, or return empty string to suppress output.

    Args:
        action: The sync action taken.
        rel_path: Relative path of the file.
        pct: Completion percentage (0–100).
        remote_index: Map of remote rel_path → ResourceEntry, used to classify new vs modified.
        verbose: If True, include SKIPPED lines.
        error: Error message when action is FAILED.

    Returns:
        Formatted progress string, or empty string if the action should not be printed.
    """
    prefix = f"[{pct:3d}%] "
    labels: dict[SyncAction, str] = {
        SyncAction.UPLOADED: f"{prefix}↑ {rel_path}  ({'new' if rel_path not in remote_index else 'modified'})",
        SyncAction.CONFLICT: f"{prefix}! {rel_path}  (conflict: modified on both sides, skipping)",
        SyncAction.INVALID: f"{prefix}! {rel_path}  (not well-formed XML, skipping)",
        SyncAction.FAILED: f"{prefix}! {rel_path}  (error: {error})",
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
    error: str = "",
) -> str:
    """Format the progress line for a pull action, or return empty string to suppress output.

    Args:
        action: The sync action taken.
        rel_path: Relative path of the file.
        pct: Completion percentage (0–100).
        is_new: True if the file was not previously in the manifest.
        verbose: If True, include SKIPPED lines.
        error: Error message when action is FAILED.

    Returns:
        Formatted progress string, or empty string if the action should not be printed.
    """
    prefix = f"[{pct:3d}%] "
    labels: dict[SyncAction, str] = {
        SyncAction.DOWNLOADED: f"{prefix}↓ {rel_path}  ({'new' if is_new else 'modified'})",
        SyncAction.CONFLICT: f"{prefix}! {rel_path}  (conflict: modified on both sides, skipping)",
        SyncAction.FAILED: f"{prefix}! {rel_path}  (error: {error})",
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
) -> tuple[dict[SyncAction, int], bool]:
    """Run the push file loop sequentially, stopping on the first failure.

    Used when ``--fail-fast`` is active to guarantee that no file after the
    first conflict, invalid XML, or transfer error is ever transferred.

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

    Returns:
        Tuple of (counts, fail_fast_triggered).
    """
    counts: dict[SyncAction, int] = {}
    total = len(local_files)
    for i, local_file in enumerate(local_files, 1):
        rel_path = local_file.relative_to(source).as_posix()
        remote_mtime = remote_index[rel_path].last_modified or "" if rel_path in remote_index else ""
        try:
            action, new_entry = _push_file_task(
                client, full_path, local_file, rel_path, remote_mtime,
                manifest.get(rel_path), rel_path in manifest, force, dry_run,
            )
            error = ""
        except Exception as exc:
            action, new_entry, error = SyncAction.FAILED, None, str(exc)
        pct = int(i / total * 100) if total else 100
        label = _push_label(action, rel_path, pct, remote_index, verbose, error)
        if label:
            typer.echo(label)
        counts[action] = counts.get(action, 0) + 1
        if not dry_run and new_entry is not None:
            manifest.set(rel_path, new_entry)
        manifest.maybe_save()
        if action in {SyncAction.INVALID, SyncAction.CONFLICT, SyncAction.FAILED}:
            return counts, True
    return counts, False


def _drain_futures(
    executor: ThreadPoolExecutor,
    futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int, str], str]]],
    manifest: Manifest,
    total: int,
    dry_run: bool,
) -> dict[SyncAction, int]:
    """Drain a futures dict produced by a parallel sync loop.

    Iterates completed futures in arrival order, prints progress labels, updates
    action counts and the manifest, and handles KeyboardInterrupt cleanly. A
    future that raises is marked SyncAction.FAILED and reported immediately;
    the drain continues with the remaining futures rather than aborting, so a
    single failed transfer doesn't stall progress output while the rest of
    the pool keeps running silently.

    Args:
        executor: The active ThreadPoolExecutor owning the futures.
        futures: Map of future → (rel_path, label_fn) where label_fn(action, pct, error) → str.
        manifest: Sync manifest (mutated in place as futures complete).
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
            try:
                action, new_entry = future.result()
                error = ""
            except Exception as exc:
                action, new_entry, error = SyncAction.FAILED, None, str(exc)
            completed += 1
            pct = int(completed / total * 100) if total else 100
            label = label_fn(action, pct, error)
            if label:
                typer.echo(label)
            counts[action] = counts.get(action, 0) + 1
            if not dry_run and new_entry is not None:
                manifest.set(rel_path, new_entry)
            manifest.maybe_save()
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
        jobs: Number of parallel upload workers.

    Returns:
        Action counts.
    """
    total = len(local_files)
    tasks = [(lf, lf.relative_to(source).as_posix()) for lf in local_files]
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int, str], str]]] = {
            executor.submit(
                _push_file_task,
                client, full_path, lf, rp,
                remote_index[rp].last_modified or "" if rp in remote_index else "",
                manifest.get(rp), rp in manifest, force, dry_run,
            ): (rp, lambda a, p, err, _rp=rp: _push_label(a, _rp, p, remote_index, verbose, err))
            for lf, rp in tasks
        }
        return _drain_futures(executor, futures, manifest, total, dry_run)


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
        jobs: Number of parallel download workers.

    Returns:
        Action counts.
    """
    total = len(resources)
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures: dict[Future[tuple[SyncAction, ManifestEntry | None]], tuple[str, Callable[[SyncAction, int, str], str]]] = {
            executor.submit(
                _pull_file_task,
                client, full_path, dest, resource.rel_path, resource.entry.last_modified or "",
                manifest.get(resource.rel_path), resource.rel_path in manifest, force, dry_run,
            ): (
                resource.rel_path,
                lambda a, p, err, _rp=resource.rel_path, _new=(resource.rel_path not in manifest): _pull_label(a, _rp, p, _new, verbose, err),
            )
            for resource in resources
        }
        return _drain_futures(executor, futures, manifest, total, dry_run)


def _push(
    source: Path,
    nick: str,
    path: str,
    force: bool,
    fail_fast: bool,
    dry_run: bool,
    delete: bool,
    exclude: list[str],
    clear_exclude: bool,
    yes: bool,
    keep_excluded: bool,
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
        exclude: Patterns to merge into the stored exclude list for this pair.
        clear_exclude: If True, clear the stored exclude list before merging.
        yes: If True, skip the confirmation prompt when deleting previously
            synced files that are now excluded.
        keep_excluded: If True, keep previously synced copies of newly
            excluded paths and only stop tracking them.
        checkpoint_every: Save the manifest after every N mutations.
        verbose: If True, also print unchanged (skipped) files.
        jobs: Number of parallel upload workers.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path, source, checkpoint_every)
    excludes = _resolve_excludes(manifest, exclude, clear_exclude)
    counts: dict[SyncAction, int] = {}
    fail_fast_triggered = False

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                excluded_deleted = _cleanup_newly_excluded(
                    client, full_path, source, manifest, excludes, yes, keep_excluded, dry_run
                )

                tree = _filter_tree(_walk_remote(client, full_path, max_workers=jobs), excludes)
                remote_index = {r.rel_path: r.entry for r in tree.resources}

                all_paths = [
                    p for p in source.rglob("*")
                    if not _is_excluded(p.relative_to(source).as_posix(), excludes)
                ]
                local_files = sorted(p for p in all_paths if p.is_file())
                local_dirs = {p.relative_to(source).as_posix() for p in all_paths if p.is_dir()}
                local_file_rels = {p.relative_to(source).as_posix() for p in local_files}

                _ensure_remote_dirs(client, full_path, local_dirs, tree.subcollections, dry_run)

                if fail_fast:
                    counts, fail_fast_triggered = _run_push_sequential(
                        client, full_path, local_files, source, remote_index,
                        manifest, force, dry_run, verbose,
                    )
                else:
                    counts = _run_push_parallel(
                        client, full_path, local_files, source, remote_index,
                        manifest, force, dry_run, verbose, jobs,
                    )

                if tree.failed:
                    counts[SyncAction.FAILED] = counts.get(SyncAction.FAILED, 0) + len(tree.failed)

                if not fail_fast_triggered and delete:
                    deleted = _delete_remote_extras(
                        client, full_path, local_file_rels, tree.resources, manifest, dry_run
                    )
                    deleted += _delete_empty_remote_dirs(
                        client, full_path, source, excludes, dry_run, max_workers=jobs
                    )
                    counts[SyncAction.DELETED] = deleted

                if excluded_deleted:
                    counts[SyncAction.DELETED] = counts.get(SyncAction.DELETED, 0) + excluded_deleted

                if not dry_run and counts.get(SyncAction.UPLOADED, 0):
                    _refresh_remote_mtimes(client, full_path, manifest, jobs)
    except KeyboardInterrupt:
        if not dry_run:
            manifest.save()
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)

    if not dry_run:
        manifest.save()
        invalidate(nick)

    _print_summary(counts)

    if fail_fast_triggered or counts.get(SyncAction.FAILED, 0):
        raise typer.Exit(1)


def _pull(
    nick: str,
    path: str,
    dest: Path,
    force: bool,
    dry_run: bool,
    delete: bool,
    exclude: list[str],
    clear_exclude: bool,
    yes: bool,
    keep_excluded: bool,
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
        exclude: Patterns to merge into the stored exclude list for this pair.
        clear_exclude: If True, clear the stored exclude list before merging.
        yes: If True, skip the confirmation prompt when deleting previously
            synced files that are now excluded.
        keep_excluded: If True, keep previously synced copies of newly
            excluded paths and only stop tracking them.
        checkpoint_every: Save the manifest after every N mutations.
        verbose: If True, also print unchanged (skipped) files.
        jobs: Number of parallel download workers.
    """
    collection, server, full_path = resolve_collection(nick, path)
    manifest = _load_manifest(nick, path, dest, checkpoint_every)
    excludes = _resolve_excludes(manifest, exclude, clear_exclude)
    counts: dict[SyncAction, int] = {}

    try:
        with handle_exist_errors(path, nick, collection.server_nick):
            with ExistClient(server) as client:
                excluded_deleted = _cleanup_newly_excluded(
                    client, full_path, dest, manifest, excludes, yes, keep_excluded, dry_run
                )

                tree = _filter_tree(_walk_remote(client, full_path, max_workers=jobs), excludes)
                _ensure_local_dirs(dest, tree.subcollections, dry_run)

                counts = _run_pull_parallel(
                    client, full_path, dest, tree.resources,
                    manifest, force, dry_run, verbose, jobs,
                )

                if tree.failed:
                    counts[SyncAction.FAILED] = counts.get(SyncAction.FAILED, 0) + len(tree.failed)

                if delete:
                    deleted = _delete_local_extras(dest, tree.resources, manifest, excludes, dry_run)
                    deleted += _delete_empty_local_dirs(dest, excludes, dry_run)
                    counts[SyncAction.DELETED] = counts.get(SyncAction.DELETED, 0) + deleted

                if excluded_deleted:
                    counts[SyncAction.DELETED] = counts.get(SyncAction.DELETED, 0) + excluded_deleted
    except KeyboardInterrupt:
        if not dry_run:
            manifest.save()
        typer.echo("\nInterrupted.", err=True)
        raise typer.Exit(130)

    if not dry_run:
        manifest.save()

    _print_summary(counts)

    if counts.get(SyncAction.FAILED, 0):
        raise typer.Exit(1)


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
    exclude: list[str] = typer.Option([], "--exclude", "-e", help="Glob pattern to exclude from the sync (repeatable); merged into the list stored for this sync pair."),
    clear_exclude: bool = typer.Option(False, "--clear-exclude", help="Clear the stored exclude list before applying any --exclude patterns."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt when deleting previously synced files that are now excluded."),
    keep_excluded: bool = typer.Option(False, "--keep-excluded", help="Keep previously synced copies of newly excluded paths on both sides (only stop tracking them)."),
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
        _push(
            source_path, nick, path, force, fail_fast, dry_run, delete,
            exclude, clear_exclude, yes, keep_excluded, checkpoint_every, verbose, jobs,
        )
    else:
        nick, path = parse_target(source, path_required=False)
        _pull(
            nick, path, Path(dest), force, dry_run, delete,
            exclude, clear_exclude, yes, keep_excluded, checkpoint_every, verbose, jobs,
        )
