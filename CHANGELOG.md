# Changelog

## unreleased

### Enhancements

- **Parallel sync (`--jobs N`)**: uploads, downloads, and remote directory listings now run concurrently. The `--jobs N` flag (default: 4) controls the number of parallel workers. Use `--jobs 1` to restore fully sequential behaviour.
- **Clean Ctrl+C handling**: interrupting a sync now exits with code 130, saves the manifest (so the next run can resume), and prints a single `Interrupted.` message instead of a Python traceback.
- **`exsh find`**: locate documents by XPath predicate anywhere in their content (`exsh find <nick>[:<path>] --query 'foo[@type="draft"]'`), with `--remove`/`--yes` to delete every match in one step.

## 0.1.2 - 2026-06-23

### Documentation

- Document installing `exsh` from PyPI (`uv tool install`, `pipx install`, `uvx --from`); the existing `git+https://...` instructions are kept as an alternative for tracking unreleased commits

## 0.1.1 - 2026-06-23

### Fixes

- Complete PyPI project metadata: `readme`, `license` (MIT), `authors`, `classifiers`, `project.urls`, and `keywords` were all missing, leaving the 0.1.0 PyPI listing with no description, license, or links
- Add `LICENSE` file (MIT)

## 0.1.0 - 2026-06-23

### Commands

| Command | Description |
|---------|-------------|
| `server add / ls / rm` | Register, list, and remove eXist-db server configurations; `rm` cascade-removes associated collections |
| `server rename <old> <new>` | Rename a server nick; all registered collections are updated automatically |
| `collection add / new / ls / rm` | Manage named collection shortcuts; `new` creates the collection on the server and registers it in one step (idempotent: no-op if already exists) |
| `ls [path]` | List documents and sub-collections at a remote path; `--sort name\|time`, `--reverse`, `--names-only` |
| `cat <path>` | Print a remote document to stdout; `--raw` skips binary detection |
| `put <path>` | Upload a document from stdin or a local file; auto-detects MIME type |
| `cp <src> <dst>` | Copy documents local↔remote or remote↔remote |
| `rm <path...>` | Delete one or more remote documents |
| `mkdir <path>` | Create a remote collection (idempotent) |
| `edit <path>` | Download, open in `$VISUAL`/`$EDITOR`, re-upload if changed |
| `sync push/pull <dir> <path>` | Sync a local directory tree with a remote collection; supports `--delete`, `--dry-run`, `--force` |
| `mv <src> <dst>` | Move or rename a document or collection; trailing `/` on dest moves into that collection; cross-server moves not supported |
| `exec <nick>[:<path>]` | Read an XQuery script from a file or stdin, optionally preprocess it (version declaration, functx import), validate locally with BaseX or Saxon (auto-detected via PATH), then execute against eXist and print the result; supports `--no-fix`, `--no-validate`, `--validator`, `--list-validators` |
| `user ls` | List user accounts and their groups; accepts `@server` positional |
| `user add <user[@server]>` | Create a user account (prompts for password) |
| `user rm <user[@server]>` | Remove a user account |
| `user info <user[@server]>` | Show user account details |
| `user passwd <user[@server]>` | Change a user's password; `--stdin` for scripting |
| `group ls` | List groups and their members; accepts `@server` positional |
| `group add <group[@server]>` | Create a group |
| `group rm <group[@server]>` | Remove a group |
| `chown <spec> <path>` | Change owner and/or group of a document or collection; `--recursive / -R` for collections; spec forms: `owner`, `:group`, `owner:group` |
| `chmod <mode> <path>` | Change POSIX permissions of a document or collection; `--recursive / -R` for collections; accepts octal (`0755`) or symbolic (`u+x`, `go-w`, `a=rw`) modes |

### Infrastructure

- Shell completion for collection/document paths (with TTL cache)
- `<name>@<server>` syntax for ad-hoc server targeting in `collection add`, `collection new`, `user *`, and `group *`
- `--server` option on all commands completes registered server nicks
- Shell completion for `<name>@<server>` and `@<server>` argument forms
- Path traversal validation and URL encoding
- Google-style docstrings enforced via ruff
- CI: pytest + coverage (Codecov), ruff, ty, e2e test suite against live eXist-db in Docker
- CI: sticky PR comments for tests (counts + coverage), ruff, ty, and e2e workflows
- CI: e2e workflow with dynamic image matrix from `--list-images`; `fail-fast: false`
