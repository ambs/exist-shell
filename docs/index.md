# exsh — eXist-db Shell

[![Tests](https://github.com/ambs/exist-shell/actions/workflows/tests.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/tests.yml)
[![Coverage](https://codecov.io/gh/ambs/exist-shell/graph/badge.svg)](https://codecov.io/gh/ambs/exist-shell)
[![e2e](https://github.com/ambs/exist-shell/actions/workflows/e2e.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/e2e.yml)
[![Ruff](https://github.com/ambs/exist-shell/actions/workflows/ruff.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/ruff.yml)
[![ty](https://github.com/ambs/exist-shell/actions/workflows/ty.yml/badge.svg)](https://github.com/ambs/exist-shell/actions/workflows/ty.yml)

**exsh** is a command-line tool to interact with an [eXist-db](https://exist-db.org) server via its REST API. It is designed for shell scripting and pipe-friendly workflows.

## Features

- Browse, read, upload, copy, edit, and delete documents on an eXist-db server
- Create and manage collections
- Bidirectional sync between local folders and remote collections
- Register multiple servers and collections with short nicknames
- Tab-completion for collection and document paths
- Usable as a Python library via `ExistClient`

## Quick start

```bash
# 1. Install
uv tool install exist-shell

# 2. Register your server
exsh server add localhost --port 8080 --user admin

# 3. Check it is reachable
exsh ping localhost

# 4. Register a collection
exsh collection add mydata@localhost

# 5. Browse
exsh ls mydata
```

See [Installation](installation.md) and [Configuration](configuration.md) for full details.

## Commands at a glance

| Command | Description |
|---------|-------------|
| `exsh ls <nick>[:<path>]` | List subcollections and documents |
| `exsh cat <nick>:<path>` | Print a document to stdout |
| `exsh put <file> <nick>:<path>` | Upload a local file |
| `exsh cp <src> <dst>` | Copy a document (local ↔ remote or remote ↔ remote) |
| `exsh mv <src> <dst>` | Move or rename a document or collection |
| `exsh edit <nick>:<path>` | Open a document in `$EDITOR`, re-upload if changed |
| `exsh rm <nick>:<path>...` | Delete one or more documents |
| `exsh mkdir <nick>:<path>` | Create a collection |
| `exsh chown <spec> <nick>:<path>` | Change owner and/or group; `-R` for recursive |
| `exsh sync <src> <dst>` | Sync a local folder and a remote collection |
| `exsh exec <nick>[:<path>]` | Execute an XQuery script on the server |
| `exsh ping [nick]` | Check server connectivity, version, and latency |
| `exsh server add <host>` | Register a server |
| `exsh server ls` | List registered servers |
| `exsh server rm <nick>` | Remove a server |
| `exsh server rename <old> <new>` | Rename a server nick |
| `exsh server status [nick]` | Same as `exsh ping` |
| `exsh collection add <name>[@<server>]` | Register a collection |
| `exsh collection new <name>[@<server>]` | Create and register a collection |
| `exsh collection ls` | List registered collections |
| `exsh collection rm <nick>` | Remove a collection from the config |
| `exsh user ls` | List user accounts and their groups |
| `exsh user add <user[@server]>` | Create a user account |
| `exsh user rm <user[@server]>` | Remove a user account |
| `exsh user info <user[@server]>` | Show user account details |
| `exsh user passwd <user[@server]>` | Change a user's password |
| `exsh group ls` | List groups and their members |
| `exsh group add <group[@server]>` | Create a group |
| `exsh group rm <group[@server]>` | Remove a group |
