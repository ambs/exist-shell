# exsh — eXist-db Shell

[![Tests](https://github.com/ambs/exist-shell/actions/workflows/tests.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/tests.yml)
[![Coverage](https://codecov.io/gh/ambs/exist-shell/graph/badge.svg)](https://codecov.io/gh/ambs/exist-shell)
[![e2e](https://github.com/ambs/exist-shell/actions/workflows/e2e.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/e2e.yml)
[![Ruff](https://github.com/ambs/exist-shell/actions/workflows/ruff.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/ruff.yml)
[![ty](https://github.com/ambs/exist-shell/actions/workflows/ty.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/ty.yml)
[![docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue)](https://ambs.github.io/exist-shell/)

A command-line tool to interact with an [eXist-db](https://exist-db.org) server via its REST API. Designed for shell scripting and pipe-friendly workflows.

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## Installation

Install system-wide with `uv tool`:

```bash
uv tool install git+https://github.com/ambs/exist-shell
```

This places `exsh` on your `PATH`. Verify with:

```bash
exsh --version
```

To uninstall:

```bash
uv tool uninstall exist-shell
```

## Configuration

### Add a server

```bash
exsh server add localhost --port 8080 --user admin
```

A nickname is derived from the hostname by default (e.g. `localhost`). Override with `--nick`.

### Add an existing collection

```bash
exsh collection add mydata@localhost
```

This registers the `/db/mydata` collection on the `localhost` server under the nick `mydata`.

### Create and register a new collection

```bash
exsh collection new mydata@localhost
```

Creates `/db/mydata` on the server and registers it in one step. If the collection already exists, it prints a message and exits without modifying the config. Use `--nick` to register it under a different name:

```bash
exsh collection new mydata@localhost --nick md
```

List configured servers and collections:

```bash
exsh server ls
exsh collection ls
```

Configuration is stored at `~/.config/exsh/config.toml`.

## Commands

| Command | Description |
|---------|-------------|
| `exsh ls <nick>[:<path>]` | List subcollections and documents at a path |
| `exsh cat <nick>:<path>` | Print a document to stdout |
| `exsh put <file> <nick>:<path>` | Upload a local file to a collection |
| `exsh cp <src> <dst>` | Copy a document (local ↔ remote or remote ↔ remote) |
| `exsh edit <nick>:<path>` | Open a document in `$EDITOR`, re-upload if changed |
| `exsh rm <nick>:<path>...` | Delete one or more documents |
| `exsh mkdir <nick>:<path>` | Create a collection |
| `exsh sync <local> <nick>[:<path>]` | Push a local folder to a remote collection |
| `exsh sync <nick>[:<path>] <local>` | Pull a remote collection to a local folder |
| `exsh exec <nick>[:<path>]` | Execute an XQuery script on a server |
| `exsh server add <host>` | Register a server |
| `exsh server ls` | List registered servers |
| `exsh server rm <nick>` | Remove a server (and its collections) |
| `exsh server rename <old> <new>` | Rename a server nick (updates collection references) |
| `exsh collection add <name>[@<server>]` | Register an existing collection |
| `exsh collection new <name>[@<server>]` | Create a collection on the server and register it |
| `exsh collection ls` | List registered collections |
| `exsh collection rm <nick>` | Remove a collection from the config |

### Examples

```bash
# List the root of a collection
exsh ls mydata

# List a subdirectory
exsh ls mydata:reports/2025

# Print a document
exsh cat mydata:reports/2025/summary.xml

# Upload a file
exsh put report.xml mydata:reports/2025/report.xml

# Copy from remote to local
exsh cp mydata:reports/2025/report.xml ./report.xml

# Edit in place
exsh edit mydata:reports/2025/report.xml

# Delete a document
exsh rm mydata:reports/2025/old.xml

# Delete multiple documents
exsh rm mydata:reports/2025/a.xml mydata:reports/2025/b.xml

# Create a subcollection
exsh mkdir mydata:reports/2026

# Execute an XQuery script from a file
exsh exec mydata:/ -f query.xq

# Execute an XQuery script from stdin
echo 'count(collection("/db/mydata"))' | exsh exec mydata:/

# Execute without local preprocessing
exsh exec mydata:/ --no-fix -f query.xq

# List locally available XQuery validators
exsh exec --list-validators

# Push a local folder to the server (only transfers changed files)
exsh sync ./reports mydata:reports

# Pull a remote collection to a local folder
exsh sync mydata:reports ./reports

# Preview what would be transferred without doing it
exsh sync --dry-run ./reports mydata:reports

# Push and remove files on the server that no longer exist locally
exsh sync --delete ./reports mydata:reports
```

## Sync

`exsh sync` transfers only files that have changed, using a local manifest stored at `~/.cache/exsh/sync/`. Direction is inferred from the argument order: local-first means push, remote-first means pull.

**Change detection:**
- **Push**: SHA-256 hash of the local file is compared against the manifest. Same-size edits are caught.
- **Pull**: `last_modified` timestamp from the eXist listing is compared against the manifest.

**Conflicts** (both sides changed since last sync) are reported and skipped — use `--force` to override.

**Options:**

| Flag | Effect |
|------|--------|
| `--force` / `-f` | Transfer all files, bypassing change detection |
| `--dry-run` / `-n` | Show what would happen without transferring |
| `--delete` | Remove files and empty folders on the destination that no longer exist on the source |
| `--checkpoint-every N` | Flush the manifest every N files (default: 100); allows interrupted syncs to resume near the point of failure |

## Shell completion

Generate and install tab-completion for your shell:

```bash
# bash
exsh --install-completion bash

# zsh
exsh --install-completion zsh

# fish
exsh --install-completion fish
```

## Development

```bash
git clone https://github.com/ambs/exist-shell
cd exist-shell
uv sync
exsh --help
```

Run checks:

```bash
make checks   # lint, type-check, and tests
make test     # tests only
```
