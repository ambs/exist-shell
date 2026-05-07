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
| T05 | [x]    | put (file, stdin, MIME, binary, overwrite, errors) |
| T06 | [x]    | ls (after uploads, including auto-created subcollections from T05.10) |
| T07 | [ ]    | cat (text, binary, --raw, errors) |
| T08 | [ ]    | cp (local→remote, remote→local, remote→remote, trailing slash, errors) |
| T09 | [ ]    | rm (single, multi, not-found, errors) |
| T10 | [ ]    | mkdir (create, idempotent, nested, errors) |
| T11 | [ ]    | edit (modified, no-change, editor error, not-found) |
| T12 | [ ]    | sync (push, unchanged, modified, dry-run, pull, --delete, conflict, --force, errors) |
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
| T05.1  | ~~`exsh put testcol:/hello.xml -f $TMPDIR_E2E/hello.xml`~~ | ✓ exit 0 |
| T05.2  | ~~repeat T05.1 (silent overwrite)~~ | ✓ exit 0 |
| T05.3  | ~~`exsh put testcol:/hello.xml -f ... --mime application/xml`~~ | ✓ exit 0 |
| T05.4  | ~~`echo '<from>stdin</from>' \| exsh put testcol:/stdin.xml`~~ | ✓ exit 0 |
| T05.5  | ~~`exsh put testcol:/data.bin -f $TMPDIR_E2E/data.bin`~~ | ✓ exit 0 |
| T05.6  | ~~`exsh put testcol:/../escape.xml ...`~~ | ✓ exit 1, `path traversal not allowed` |
| T05.7  | ~~`exsh put testcol -f ...` (no colon/path)~~ | ✓ exit 1, `path is required` |
| T05.8  | ~~`exsh put testcol:/x.xml -f /nonexistent/file.xml`~~ | ✓ exit 1, `cannot read` |
| T05.9  | ~~`exsh put ghost:/x.xml ...`~~ | ✓ exit 1, `collection 'ghost' not found` |
| T05.10 | ~~`exsh put testcol:/missing/sub/doc.xml -f $TMPDIR_E2E/hello.xml`~~ | ✓ exit 0 — eXist auto-creates intermediate collections; T06 verifies `/missing/sub/` and `doc.xml` appear in listings |

Files created in this section (persist for T06+):
- `$TMPDIR_E2E/hello.xml` → `<hello>world</hello>`
- `$TMPDIR_E2E/data.bin` → small binary (`\x00\x01\x02\x03`)

---

## T06 subtasks — ls (after uploads)

Preconditions: T05 has run. Remote state in `testcol` (`/db/testcol`):
- `hello.xml`, `stdin.xml`, `data.bin` in root
- `missing/` subcollection (auto-created by T05.10)
- `missing/sub/` nested subcollection
- `missing/sub/doc.xml` document

| ID    | Command | Expected |
|-------|---------|----------|
| T06.1 | ~~`exsh ls testcol`~~ | ✓ exit 0, output contains `hello.xml` |
| T06.2 | ~~`exsh ls testcol`~~ | ✓ exit 0, output contains `stdin.xml` |
| T06.3 | ~~`exsh ls testcol`~~ | ✓ exit 0, output contains `data.bin` |
| T06.4 | ~~`exsh ls testcol`~~ | ✓ exit 0, output contains `missing/` (subcollections printed with trailing slash) |
| T06.5 | ~~`exsh ls testcol:/missing`~~ | ✓ exit 0, output contains `sub/` |
| T06.6 | ~~`exsh ls testcol:/missing/sub`~~ | ✓ exit 0, output contains `doc.xml` |

---

## T07 subtasks — cat (text, binary, errors)

Preconditions: T05 files are present. `hello.xml` contains `<hello>world</hello>`, `stdin.xml` contains `<from>stdin</from>`, `data.bin` is binary.

Error messages:
- binary without `--raw` → `"Error: '…' is binary (…). Use --raw to write bytes to stdout."` (from `cat.py`)
- path not found → `"Error: path '…' not found in collection '…'."` (from `handle_exist_errors`)
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- path required → `"Error: path is required (use <nick>:<path>)."` (from `parse_target`)

| ID    | Command | Expected |
|-------|---------|----------|
| T07.1 | `exsh cat testcol:/hello.xml` | exit 0, output contains `<hello>world</hello>` |
| T07.2 | `exsh cat testcol:/stdin.xml` | exit 0, output contains `<from>stdin</from>` |
| T07.3 | `exsh cat testcol:/data.bin` | exit 1, output contains `is binary` |
| T07.4 | `exsh cat testcol:/data.bin --raw > $TMPDIR_E2E/data_dl.bin` | exit 0, `data_dl.bin` matches original `data.bin` |
| T07.5 | `exsh cat testcol:/nonexistent.xml` | exit 1, output contains `not found in collection` |
| T07.6 | `exsh cat ghost:/hello.xml` | exit 1, output contains `collection 'ghost' not found` |
| T07.7 | `exsh cat testcol` (no colon/path) | exit 1, output contains `path is required` |

T07.4 note: `--raw` writes bytes to `sys.stdout.buffer`, so redirect to a file and use `assert_file_eq` or `cmp` to verify the content.

---

## T08 subtasks — cp (local→remote, remote→local, remote→remote, errors)

Preconditions: T05 files are present. `testcol` and `testcol2` both point to `/db/testcol` on `localhost`.

Error messages:
- both local → `"Error: at least one of source or target must be a remote path (nick:path)."` (from `cp.py`)
- unreadable source → `"Error: cannot read '…': …"` (from `cp.py` OSError handler)
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- path not found → `"Error: path '…' not found in collection '…'."` (from `handle_exist_errors`)

| ID     | Command | Expected |
|--------|---------|----------|
| T08.1  | `exsh cp $TMPDIR_E2E/hello.xml testcol:/hello_copy.xml` | exit 0 (local→remote) |
| T08.2  | `exsh ls testcol` | exit 0, output contains `hello_copy.xml` |
| T08.3  | `exsh cp testcol:/hello.xml $TMPDIR_E2E/hello_dl.xml` | exit 0 (remote→local) |
| T08.4  | `cat $TMPDIR_E2E/hello_dl.xml` | output contains `<hello>world</hello>` |
| T08.5  | `exsh cp testcol:/hello.xml testcol2:/hello_r2r.xml` | exit 0 (remote→remote, different nicks same server) |
| T08.6  | `exsh ls testcol` | exit 0, output contains `hello_r2r.xml` |
| T08.7  | `exsh cp testcol:/hello.xml testcol:/` (trailing slash) | exit 0, uploads as `/hello.xml` (overwrites) |
| T08.8  | `exsh cp $TMPDIR_E2E/hello.xml $TMPDIR_E2E/copy.xml` (both local) | exit 1, `at least one of source or target` |
| T08.9  | `exsh cp /nonexistent.xml testcol:/nope.xml` | exit 1, `cannot read` |
| T08.10 | `exsh cp ghost:/hello.xml $TMPDIR_E2E/x.xml` | exit 1, `collection 'ghost' not found` |

Files created in this section (persist for T09):
- `testcol:/hello_copy.xml`
- `testcol:/hello_r2r.xml`

---

## T09 subtasks — rm (single, multi, not-found, errors)

Preconditions: T08 has created `hello_copy.xml` and `hello_r2r.xml` in `testcol`.

Error messages:
- path not found → `"Error: path '…' not found in collection '…'."` (from `handle_exist_errors`)
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- path required → `"Error: path is required (use <nick>:<path>)."` (from `parse_target`)

| ID    | Command | Expected |
|-------|---------|----------|
| T09.1 | `exsh rm testcol:/hello_copy.xml` | exit 0 |
| T09.2 | `exsh ls testcol` | exit 0, output does not contain `hello_copy.xml` |
| T09.3 | `exsh rm testcol:/stdin.xml testcol:/hello_r2r.xml` | exit 0 (multi-target in one call) |
| T09.4 | repeat T09.1 (already deleted) | exit 1, output contains `not found in collection` |
| T09.5 | `exsh rm ghost:/x.xml` | exit 1, output contains `collection 'ghost' not found` |
| T09.6 | `exsh rm testcol` (no colon/path) | exit 1, output contains `path is required` |

T09.2 note: use `assert_output_absent` or run `exsh ls testcol` and grep for the absence of `hello_copy.xml`.

---

## T10 subtasks — mkdir (create, idempotent, nested, errors)

Preconditions: `testcol` is registered. `create_collection` uses the `.keep`/delete pattern so it is idempotent.

Error messages:
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)
- path required → `"Error: path is required (use <nick>:<path>)."` (from `parse_target`)

| ID     | Command | Expected |
|--------|---------|----------|
| T10.1  | `exsh mkdir testcol:/newdir` | exit 0 |
| T10.2  | `exsh ls testcol` | exit 0, output contains `newdir` |
| T10.3  | repeat T10.1 (collection already exists) | exit 0 (idempotent — eXist treats duplicate PUT as a no-op) |
| T10.4  | `exsh mkdir testcol:/nested/deep` | exit 0 (eXist auto-creates `nested` when PUT to `nested/deep/.keep`) |
| T10.5  | `exsh ls testcol` | exit 0, output contains `nested` |
| T10.6  | `exsh ls testcol:/nested` | exit 0, output contains `deep` |
| T10.7  | `exsh mkdir ghost:/newdir` | exit 1, output contains `collection 'ghost' not found` |
| T10.8  | `exsh mkdir testcol` (no colon/path) | exit 1, output contains `path is required` |

---

## T11 subtasks — edit (modified, no-change, editor error, not-found)

Preconditions: `testcol:/hello.xml` contains `<hello>world</hello>`.

Editor resolution order: `$VISUAL` → `$EDITOR` → `vi`. Tests use `EDITOR=…` overrides.

Fake editor script: write `${TMPDIR_E2E}/fake_editor.sh` using `perl -i -pe 's/world/eXist/'` (cross-platform; avoids `sed -i` BSD/GNU incompatibility).

Error messages:
- editor non-zero exit → `"Error: editor exited with code N."` (from `edit.py`)
- no changes → `"No changes."` (stdout, exit 0)
- path not found → `"Error: path '…' not found in collection '…'."` (from `handle_exist_errors`)
- unknown nick → `"Error: collection '…' not found."` (from `resolve_collection`)

| ID     | Command | Expected |
|--------|---------|----------|
| T11.1  | create `${TMPDIR_E2E}/fake_editor.sh` (perl replace world→eXist); `chmod +x` | setup |
| T11.2  | `EDITOR="${TMPDIR_E2E}/fake_editor.sh" exsh edit testcol:/hello.xml` | exit 0 (content changed → re-uploaded) |
| T11.3  | `exsh cat testcol:/hello.xml` | exit 0, output contains `eXist` (and no longer `world`) |
| T11.4  | `EDITOR=true exsh edit testcol:/hello.xml` | exit 0, output contains `No changes.` (`true` exits 0 without touching the file) |
| T11.5  | `EDITOR=false exsh edit testcol:/hello.xml` | exit 1, output contains `editor exited with code` (`false` exits 1) |
| T11.6  | `EDITOR=true exsh edit testcol:/nonexistent.xml` | exit 1, output contains `not found in collection` |
| T11.7  | `EDITOR=true exsh edit ghost:/hello.xml` | exit 1, output contains `collection 'ghost' not found` |

---

## T12 subtasks — sync (push, unchanged, modified, dry-run, pull, --delete, conflict, --force, errors)

Preconditions: `testcol` registered on `localhost`. Uses `testcol:/syncroot` as the remote path.

Output markers (from `sync.py`):
- new upload → `"↑ {rel}  (new)"`
- modified upload → `"↑ {rel}  (modified)"`
- new download → `"↓ {rel}  (new)"`
- unchanged → `"= {rel}  (unchanged)"`
- conflict → `"! {rel}  (conflict: modified on both sides, skipping)"`
- deleted → `"✗ {rel}  (deleted)"`
- summary → `"---"` on its own line

Error messages:
- both remote → `"Error: both source and destination are remote. Use cp for remote-to-remote copies."`
- both local → `"Error: one of source or destination must be a remote collection (nick:path)."`
- source not a directory → `"Error: '…' is not a directory."`
- unknown nick → `"Error: collection '…' not found."`

| ID     | Command | Expected |
|--------|---------|----------|
| T12.1  | create `${TMPDIR_E2E}/syncdir/` with `a.xml` (`<a/>`) and `b.xml` (`<b/>`) | setup |
| T12.2  | `exsh sync ${TMPDIR_E2E}/syncdir testcol:/syncroot` | exit 0, output contains `↑ a.xml  (new)` and `↑ b.xml  (new)` |
| T12.3  | `exsh ls testcol:/syncroot` | exit 0, output contains `a.xml` and `b.xml` |
| T12.4  | push again unchanged | exit 0, output contains `= a.xml  (unchanged)` and `= b.xml  (unchanged)` |
| T12.5  | overwrite `${TMPDIR_E2E}/syncdir/a.xml` with `<a2/>`; push | exit 0, output contains `↑ a.xml  (modified)` |
| T12.6  | overwrite `${TMPDIR_E2E}/syncdir/b.xml` with `<b2/>`; push with `--dry-run` | exit 0, output contains `↑ b.xml  (modified)` but no actual upload (repeat push again shows same message) |
| T12.7  | `exsh sync testcol:/syncroot ${TMPDIR_E2E}/pulldir` | exit 0, output contains `↓ a.xml  (new)` and `↓ b.xml  (new)` |
| T12.8  | `diff ${TMPDIR_E2E}/pulldir/a.xml ${TMPDIR_E2E}/syncdir/a.xml` | exit 0 (pulled file matches local after T12.5) |
| T12.9  | real push for T12.6 (without --dry-run) | exit 0, output contains `↑ b.xml  (modified)` |
| T12.10 | remove `${TMPDIR_E2E}/syncdir/b.xml`; `exsh sync … --delete` | exit 0, output contains `✗ b.xml  (deleted)` |
| T12.11 | `exsh ls testcol:/syncroot` | exit 0, output does not contain `b.xml` |
| T12.12 | conflict: `curl -X PUT` to modify `a.xml` on remote; modify local `a.xml` differently; push without `--force` | exit 0, output contains `conflict` |
| T12.13 | `exsh sync … --force` (same files) | exit 0, output contains `↑ a.xml  (new)` — force bypasses conflict detection |
| T12.14 | both remote: `exsh sync testcol:/syncroot testcol2:/other` | exit 1, `both source and destination are remote` |
| T12.15 | both local: `exsh sync ${TMPDIR_E2E}/syncdir ${TMPDIR_E2E}/pulldir` | exit 1, `one of source or destination must be a remote collection` |
| T12.16 | source not a dir: `exsh sync ${TMPDIR_E2E}/hello.xml testcol:/x` | exit 1, `is not a directory` |
| T12.17 | unknown nick: `exsh sync ${TMPDIR_E2E}/syncdir ghost:/x` | exit 1, `collection 'ghost' not found` |

T12.6 note: after --dry-run push, run the push again for real (T12.9) — if dry-run had actually uploaded, T12.9 would show `unchanged` instead of `modified`.

---

## T13 subtasks — GitHub Actions workflow

Create `.github/workflows/e2e.yml`. The Linux runner has Docker pre-installed; Colima is not needed (the `_ensure_colima` guard in `docker.sh` is macOS-only).

| ID     | Step | Notes |
|--------|------|-------|
| T13.1  | `on: push` and `on: pull_request` triggers | Run on every push and PR |
| T13.2  | `jobs.e2e` runs on `ubuntu-latest` | Docker available, no Colima |
| T13.3  | Steps: `actions/checkout`, install `uv` via `astral-sh/setup-uv`, `uv sync` | Set up Python env |
| T13.4  | Run `bash scripts/e2e.sh` | Explicit `docker pull` in script is fine on GHA (network access) |
| T13.5  | Upload test output as artifact on failure (`if: failure()`) | Easier debugging in CI |

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
