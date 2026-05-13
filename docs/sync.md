# sync

Synchronise a local directory tree with a remote eXist collection, transferring only files that have actually changed.

```
exsh sync <source> <dest> [--force] [--dry-run] [--delete] [--checkpoint-every N]
```

## Direction

Direction is inferred from the argument order:

| Arguments | Direction |
|-----------|-----------|
| `./local mydata:remote` | **Push** — local → remote |
| `mydata:remote ./local` | **Pull** — remote → local |

Both source and destination cannot be remote. For remote-to-remote copies, use [`exsh cp`](commands.md#cp).

## Change detection

`exsh sync` maintains a *manifest* file at `~/.cache/exsh/sync/` that records the last-synced state of each file.

**Push (local → remote)**

- A SHA-256 hash of the local file is compared against the manifest.
- Files with a different hash are uploaded; files with the same hash are skipped.
- Same-content renames are caught (the hash changes), including same-size edits.

**Pull (remote → local)**

- The `last_modified` timestamp from the eXist REST listing is compared against the manifest.
- Files with a newer timestamp are downloaded; unchanged files are skipped.
- If the file no longer exists locally, it is always re-downloaded.

## Conflicts

A *conflict* occurs when **both** sides have changed since the last sync:

- Push: local hash differs **and** remote `last_modified` differs.
- Pull: remote `last_modified` differs **and** the local SHA-256 no longer matches the manifest.

Conflicted files are **skipped** and reported with a `!` prefix:

```
! reports/2025/summary.xml  (conflict: modified on both sides, skipping)
```

Use `--force` to override conflict detection and transfer the source unconditionally.

## Options

| Flag | Description |
|------|-------------|
| `--force / -f` | Transfer every file, ignoring the manifest |
| `--dry-run / -n` | Print what would happen without moving any data |
| `--delete` | Remove files and empty folders on the destination that no longer exist on the source |
| `--checkpoint-every N` | Flush the manifest to disk every N files (default: 100) |

## Output

Each file is printed with a status prefix:

| Prefix | Meaning |
|--------|---------|
| `↑ file (new)` | Uploaded, did not exist remotely |
| `↑ file (modified)` | Uploaded, overwrote existing remote file |
| `↓ file (new)` | Downloaded, did not exist locally |
| `↓ file (modified)` | Downloaded, overwrote existing local file |
| `= file (unchanged)` | Skipped — no changes detected |
| `! file (conflict…)` | Skipped — modified on both sides |
| `✗ file (deleted)` | Removed from destination (only with `--delete`) |
| `+ dir/ (new collection)` | Remote collection created during push |
| `+ dir/ (new directory)` | Local directory created during pull |

A summary line is printed at the end:

```
---
3 uploadeds, 2 skipped, 1 conflict
```

## Examples

```bash
# Push local reports/ to the server
exsh sync ./reports mydata:reports

# Pull the server's reports collection locally
exsh sync mydata:reports ./reports

# Preview what a push would do
exsh sync --dry-run ./reports mydata:reports

# Push into a subdirectory of the collection
exsh sync ./reports mydata:data/reports

# Push and remove remote files that were deleted locally
exsh sync --delete ./reports mydata:reports

# Force a full push (re-upload everything regardless of state)
exsh sync --force ./reports mydata:reports
```

## Large collections and resumability

For collections with many files, the manifest is flushed to disk every 100 files by default. If a sync is interrupted (network failure, process kill, etc.), the next run reads the saved manifest and skips files that were already transferred, restarting near the point of failure rather than from scratch.

Adjust the interval with `--checkpoint-every`:

```bash
# Checkpoint every 50 files instead of the default 100
exsh sync --checkpoint-every 50 ./data myserver:data
```

Setting `--checkpoint-every 1` gives maximum resume granularity at the cost of more disk writes.

**Note on push resumability:** uploaded files are checkpointed with an empty `remote_last_modified` because the server-assigned timestamp is only captured at the end of a complete run. On restart, files with an empty mtime whose local content has not changed are correctly skipped — they will not be re-uploaded. The mtime is corrected once a full push completes successfully.

## Manifest location

Manifests are stored at:

```
~/.cache/exsh/sync/<nick>@<hash>.json
```

where `<hash>` is a 16-character SHA-256 prefix of the remote path. You can inspect or delete them manually without consequence — a missing manifest causes the next sync to treat all files as new and transfer them unconditionally.
