# Changelog

## unreleased


### Commands

| Command | Description |
|---------|-------------|
| `server add / ls` | Register and list eXist-db server configurations |
| `collection add / new / ls / rm` | Manage named collection shortcuts; `new` creates the collection on the server and registers it in one step (idempotent: no-op if already exists) |
| `ls [path]` | List documents and sub-collections at a remote path |
| `cat <path>` | Print a remote document to stdout; `--raw` skips binary detection |
| `put <path>` | Upload a document from stdin or a local file; auto-detects MIME type |
| `cp <src> <dst>` | Copy documents local↔remote or remote↔remote |
| `rm <path...>` | Delete one or more remote documents |
| `mkdir <path>` | Create a remote collection (idempotent) |
| `edit <path>` | Download, open in `$VISUAL`/`$EDITOR`, re-upload if changed |
| `sync push/pull <dir> <path>` | Sync a local directory tree with a remote collection; supports `--delete`, `--dry-run`, `--force` |

### Infrastructure

- Shell completion for collection/document paths (with TTL cache)
- `<name>@<server>` syntax for ad-hoc server targeting in `collection add` and `collection new`
- `--server` option on `collection add` and `collection new` completes registered server nicks
- Path traversal validation and URL encoding
- Google-style docstrings enforced via ruff
- CI: pytest + coverage (Codecov), ruff, ty, e2e test suite against live eXist-db in Docker
- CI: sticky PR comments for tests (counts + coverage), ruff, ty, and e2e workflows
- CI: e2e workflow with dynamic image matrix from `--list-images`; `fail-fast: false`
