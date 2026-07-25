# Changelog

## unreleased

### Fixes

- `is_remote()` classified any argument containing `:` as a `nick:path` remote target, so Windows paths (`C:\data\doc.xml`) and any local path with a colon in a directory component were always misparsed as a remote nick. A prefix is now only treated as a nick when it matches a configured collection, isn't a single-letter drive prefix (`C:\`, `C:/`), and doesn't itself contain a path separator. Server/collection nicks must now be at least 2 characters, guaranteeing a configured nick can never collide with a Windows drive letter
- `mv` of a collection onto itself (`exsh mv nick:/a nick:/a`) or into itself via a trailing slash (`exsh mv nick:/a nick:/a/`) copied the contents onto/into the source and then recursively deleted it, destroying the data. `mv` now aborts with an error when the target is the same as, or nested inside, the source, for both collections and single documents
- `cat`/`cp`/`mv`/`edit`/`sync` downloading an executable resource (`.xql`, `.xqm`) ran the query on the server and returned its result instead of the document's raw source
- The above fix relied on eXist's `_source=yes` REST parameter, which requires the path to be explicitly allowlisted in the server's `descriptor.xml` — not the default for anything under `/db`, regardless of the caller's own read permission. This returned `403 Forbidden` for every executable-resource download (`.xq`, `.xql`, `.xqm`, `.xquery`, `.xqy`, `.xqws`) on an unconfigured (i.e. most) server. These resources are now fetched via `util:binary-doc()`, which only needs the read + query-eval permission already required to execute them
- `rm <nick>:<path>` on a path that is a collection silently deleted the entire subtree with no confirmation, since eXist's `DELETE` is recursive on collections. `rm` now refuses a collection target unless `--recursive`/`-r` is given, and prompts for confirmation unless `--yes`/`-y` is also passed
- `create_collection`, `is_collection`, and `move_document` embedded paths/names into generated XQuery without escaping `"`/`&`, unlike every other client method — a path or name containing either broke the query (or, in `move_document`, changed its meaning)
- `rm` and `find --remove` never invalidated the completion cache after deleting, so deleted documents kept appearing in tab completion until the cache TTL expired

### Enhancements

- **Faster, correct bash tab-completion for `nick:path` targets**: the generated bash completion script now handles the `:` word-break correctly (no more `dlp:dlp:...` insertions), completing a collection no longer needs an extra backspace before continuing into it, and completion listings are filtered and capped server-side and cached per prefix so progressive typing reuses a single fetch. Re-run `exsh --install-completion bash` after upgrading to pick up the new script.
- **Exit code 130 on Ctrl+C** for the whole CLI (previously sync-only), including during shell completion itself, which Typer/click don't handle on their own.
- **Parallel sync (`--jobs N`)**: uploads, downloads, and remote directory listings now run concurrently. The `--jobs N` flag (default: 4) controls the number of parallel workers. Use `--jobs 1` to restore fully sequential behaviour.
- **Clean Ctrl+C handling**: interrupting a sync now exits with code 130, saves the manifest (so the next run can resume), and prints a single `Interrupted.` message instead of a Python traceback.
- **`exsh find`**: locate documents by XPath expression anywhere in their content (`exsh find <nick>[:<path>] --query 'foo[@type="draft"]'`), with `--remove`/`--yes` to delete every match in one step.

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
