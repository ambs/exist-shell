# End-to-end test script — plan and progress

## Goal

`scripts/e2e.sh` exercises the real `exsh` binary against a live eXist-db instance
running in Docker. Every command is tested end-to-end; no HTTP mocking. The script
is built task-by-task so each increment can be validated before the next is added.
After T12 it runs as a full regression suite. T13 wires it into GitHub Actions.

---

## Task list

| ID  | Status | Section |
|-----|--------|---------|
| T01 | [x]    | Scaffold: helpers, Docker lifecycle, config setup/teardown, summary |
| T02 | [x]    | server add / server ls |
| T03 | [x]    | collection add / collection ls |
| T04 | [x]    | ls (empty collection, error cases) |
| T05 | [ ]    | put (file, stdin, MIME, binary, overwrite, errors) |
| T06 | [ ]    | ls (after uploads) |
| T07 | [ ]    | cat (text, binary, errors) |
| T08 | [ ]    | cp (local→remote, remote→local, remote→remote) |
| T09 | [ ]    | rm (single, multi, not-found) |
| T10 | [ ]    | mkdir (create, duplicate, errors) |
| T11 | [ ]    | edit (modified, no-change) |
| T12 | [ ]    | sync (push, pull, --delete, --dry-run, conflict) |
| T13 | [ ]    | GitHub Actions workflow (.github/workflows/e2e.yml) |

Mark tasks `[x]` as they are completed.

---

## T02 subtasks — server add / server ls

`server add` calls `check_connection()` before saving, so the Docker container must
be running. Error messages come from `server.py` catch blocks:
- connection failure → `"Error: Cannot connect to …"`
- auth failure → `"Error: authentication failed for …"`
- duplicate nick → `"Error: server nick '…' already exists."`

| ID     | Command | Expected |
|--------|---------|----------|
| T02.1  | ~~`exsh server add localhost --user admin --password ""`~~ | ✓ exit 0, output contains `Server 'localhost' added.` |
| T02.2  | ~~`exsh server ls`~~ | ✓ exit 0, output contains `localhost` and `admin@localhost:8080` |
| T02.3  | ~~repeat T02.1 (duplicate nick)~~ | ✓ exit 1, output contains `already exists` |
| T02.4  | ~~`exsh server add localhost --user admin --password "wrong" --nick badauth`~~ | ✓ exit 1, output contains `authentication failed` |
| T02.5  | ~~`exsh server add doesnotexist.local --nick ghost`~~ | ✓ exit 1, output contains `Cannot connect to` |
| T02.6  | ~~`exsh server add localhost --port 9999 --user admin --password "" --nick wrongport`~~ | ✓ exit 1, output contains `Cannot connect to` |
| T02.7  | ~~`exsh server ls` (repeat of T02.2)~~ | ✓ exit 0, still only `admin@localhost:8080` — failed adds left no trace |
| T02.8  | ~~`exsh server add localhost --user admin --password "" --nick local2`~~ | ✓ exit 0, output contains `Server 'local2' added.` |
| T02.9  | ~~`exsh server ls`~~ | ✓ exit 0, output contains both `localhost` and `local2` entries |
| T02.10 | **FIXME** `exsh server rm local2` then verify single-server default-selection works (e.g. `exsh collection add` without `--server` succeeds) — requires implementing `server rm`, which is not yet a feature. Re-register `local2` afterwards so T03 preconditions still hold. |

---

## T03 subtasks — collection add / collection ls

Preconditions: T02 has registered `localhost` and `local2` servers. Bootstrap has
created `/db/testcol` on the server. `collection add` verifies the collection exists
before saving. Error messages from `collection.py`:
- duplicate nick → `"Error: nick '…' already exists."`
- unknown server → `"Error: server '…' not found."`
- collection missing on server → `"Error: '/db/…' not found on server '…'."`
- multiple servers, no `--server` → `"Error: --server is required when multiple servers are configured."`
- conflicting `@server` and `--server` → `"Error: conflicting --server and @server in argument."`

| ID    | Command | Expected |
|-------|---------|----------|
| T03.1 | ~~`exsh collection add testcol@localhost`~~ | ✓ exit 0, output contains `Collection 'testcol' added.` |
| T03.2 | ~~`exsh collection ls`~~ | ✓ exit 0, output contains `testcol`, `/db/testcol`, `@localhost` |
| T03.3 | ~~repeat T03.1 (duplicate nick)~~ | ✓ exit 1, output contains `already exists` |
| T03.4 | ~~`exsh collection add testcol@localhost --nick testcol2`~~ | ✓ exit 0, `Collection 'testcol2' added.` (same collection, different nick) |
| T03.5 | ~~`exsh collection ls`~~ | ✓ exit 0, output contains both `testcol` and `testcol2` |
| T03.6 | ~~`exsh collection add nonexistent@localhost`~~ | ✓ exit 1, output contains `not found on server` |
| T03.7 | ~~`exsh collection add testcol@ghost`~~ | ✓ exit 1, output contains `not found` (unknown server nick) |
| T03.8 | ~~`exsh collection add testcol` (no server, two servers configured)~~ | ✓ exit 1, output contains `--server is required` |
| T03.9 | ~~`exsh collection add testcol@localhost --server local2` (conflicting)~~ | ✓ exit 1, output contains `conflicting` |
| T03.10 | **FIXME** Depends on T02.10 (`server rm`). Remove `local2`, then re-run a variant of T03.1 using `exsh collection add testcol3` (no `@server`) — should succeed by picking the sole registered server automatically. Re-add `local2` and clean up `testcol3` afterwards so later sections are unaffected. |

---

## T04 subtasks — ls (empty collection, error cases)

Preconditions: `testcol` and `testcol2` are registered (both point to `/db/testcol`
on `localhost`). The collection is still empty at this point — uploads happen in T05.

Error messages:
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- path not found → `"Error: path '…' not found in collection '…'."` (from `handle_exist_errors`)

| ID    | Command | Expected |
|-------|---------|----------|
| T04.1 | ~~`exsh ls testcol`~~ | ✓ exit 0, output is empty (no items yet) |
| T04.2 | ~~`exsh ls testcol:/`~~ | ✓ exit 0, output is empty (explicit root path, same result) |
| T04.3 | ~~`exsh ls testcol:/nonexistent`~~ | ✓ exit 1, output contains `not found in collection` |
| T04.4 | ~~`exsh ls ghost`~~ | ✓ exit 1, output contains `collection 'ghost' not found` |
| T04.5 | ~~`exsh ls ghost:/some/path`~~ | ✓ exit 1, output contains `collection 'ghost' not found` |

---

## T05 subtasks — put (file, stdin, MIME, binary, overwrite, errors)

Preconditions: `testcol` registered on `localhost`, collection is empty.
Temp files are created under `$TMPDIR_E2E` so teardown cleans them automatically.

Error messages:
- path required → `"Error: path is required (use <nick>:<path>)."` (from `parse_target`)
- path traversal → `"Error: path traversal not allowed: '…' segment"` (from `validate_path`)
- unreadable file → `"Error: cannot read '…': …"` (from `put.py` OSError handler)
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- missing parent collection on server → `"Error: path '…' not found in collection '…'."` (ExistNotFoundError → `handle_exist_errors`)

| ID    | Command | Expected |
|-------|---------|----------|
| T05.1 | `exsh put testcol:/hello.xml -f $TMPDIR_E2E/hello.xml` (XML file) | exit 0 |
| T05.2 | repeat T05.1 (silent overwrite) | exit 0 (no error, no prompt) |
| T05.3 | `exsh put testcol:/hello.xml -f $TMPDIR_E2E/hello.xml --mime application/xml` | exit 0 (explicit MIME override) |
| T05.4 | `echo '<from>stdin</from>' \| exsh put testcol:/stdin.xml` | exit 0 (read from stdin) |
| T05.5 | `exsh put testcol:/data.bin -f $TMPDIR_E2E/data.bin` (binary file, MIME guessed as `application/octet-stream`) | exit 0 |
| T05.6 | `exsh put testcol:/../escape.xml -f $TMPDIR_E2E/hello.xml` | exit 1, output contains `path traversal not allowed` |
| T05.7 | `exsh put testcol -f $TMPDIR_E2E/hello.xml` (no colon/path) | exit 1, output contains `path is required` |
| T05.8 | `exsh put testcol:/x.xml -f /nonexistent/file.xml` | exit 1, output contains `cannot read` |
| T05.9 | `exsh put ghost:/x.xml -f $TMPDIR_E2E/hello.xml` | exit 1, output contains `collection 'ghost' not found` |
| T05.10 | `exsh put testcol:/missing/sub/doc.xml -f $TMPDIR_E2E/hello.xml` | exit 1, output contains `not found in collection` |

Files created in this section (persist for T06+):
- `$TMPDIR_E2E/hello.xml` → `<hello>world</hello>`
- `$TMPDIR_E2E/data.bin` → small binary (`\x00\x01\x02\x03`)

---

## Script architecture

**File**: `scripts/e2e.sh`  
**Language**: Bash — `#!/usr/bin/env bash`, `set -euo pipefail`

### Docker lifecycle

- Image: `existdb/existdb:latest`
- Container name: `exsh-e2e`, port `8080:8080`
- Started at the top of `main`; stopped by `teardown` via `trap teardown EXIT`
- Wait loop: poll `curl -sf http://localhost:8080/exist/rest/db` every 2 s, up to 60 s

### Config isolation

`EXSH_CONFIG` is exported pointing to `$TMPDIR_E2E/config.toml`, which is
pre-seeded with `cache_dir = "$TMPDIR_E2E/cache"`. This isolates both the config
and the cache from the real `~/.config/exsh/config.toml` and `~/.cache/exsh/`.
`teardown` removes `TMPDIR_E2E` entirely. The trap is set at the top level of
`e2e.sh` (right after `mktemp`) so cleanup fires even if sourcing a section fails.

### Bootstrap

Before any `exsh` command, create `/db/testcol` directly via REST so
`exsh collection add` has something to register (it requires the collection to exist):

```bash
curl -sf -u admin: -X PUT http://localhost:8080/exist/rest/db/testcol/
```

### Helper functions

```
step <title>                   — print a section header
ok <desc>                      — print ✓, increment PASS
fail <desc>                    — print ✗, call debug_info, exit 1
debug_info                     — dump container logs, last command output, config file

assert_exit0 <desc> <cmd...>   — fail if exit code != 0
assert_exit1 <desc> <cmd...>   — fail if exit code == 0
assert_output <needle> <cmd...>— fail if stdout does not contain needle
assert_file_eq <file> <bytes>  — fail if file content doesn't match
```

All assertions capture stdout+stderr into a variable for `debug_info` to print.

### Section structure

Each task T02–T12 is a standalone Bash function (e.g. `section_server`).
`main` calls them in order. Adding a section = define the function + one call in `main`.

### Edit section (T11)

- *Modified*: write `/tmp/exsh_fake_editor.sh` that runs `sed -i 's/world/eXist/'`,
  set `EDITOR=/tmp/exsh_fake_editor.sh`.
- *No-change*: set `EDITOR=true` (exits 0 without touching the file).

### Sync section (T12)

1. Push: create local dir with files → push → verify with `exsh ls`
2. Pull: pull to new temp dir → `diff -r` against originals
3. `--dry-run`: verify no files actually transferred
4. `--delete`: push with a file removed → verify it's gone on remote
5. Conflict: push once, edit remote via `curl -X PUT`, edit local copy, push again →
   expect "conflict" in output, no upload

### Summary (printed by `teardown` or at end of `main`)

```
───────────────────────────────
  42 passed, 0 failed
  All checks passed.
```

Exit code 1 if any failure (required for GitHub Actions to fail the job).

---

## Files

| Path | Notes |
|------|-------|
| `scripts/e2e.sh` | Main script (executable) |
| `e2e_plan.md` | This file — update Status column as tasks complete |
| `.github/workflows/e2e.yml` | Added in T13 |
