# exsh — eXist-db Shell

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

### Add a collection

```bash
exsh collection add mydata@localhost
```

This registers the `/db/mydata` collection on the `localhost` server under the nick `mydata`.

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
| `exsh server add <host>` | Register a server |
| `exsh server ls` | List registered servers |
| `exsh collection add <name>[@<server>]` | Register a collection |
| `exsh collection ls` | List registered collections |

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
```

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
