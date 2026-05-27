# CLI Commands

All commands follow the pattern `exsh <command> [options]`. Paths to remote documents and collections are written as `<nick>:<path>` (e.g. `mydata:reports/2025/summary.xml`), where `<nick>` is the short name you gave to a registered collection.

## ls

List subcollections and documents at a collection path.

```
exsh ls <nick>[:<path>] [--sort name|time] [--reverse] [--names-only]
```

Output has one entry per line with columns separated by two spaces. Subcollections are shown with a trailing `/`. Empty fields (e.g. size for a collection) are omitted.

**Columns for collections:** `name/`, `permissions`, `owner`, `created`

**Columns for resources:** `name`, `permissions`, `owner`, `size (bytes)`, `mime-type`, `last-modified`

### Options

| Flag | Description |
|------|-------------|
| `--sort name` | Sort entries alphabetically by name (default) |
| `--sort time` | Sort by modification time (oldest first) |
| `--reverse / -r` | Reverse the sort order |
| `--names-only` | Print only names, one per line — useful for piping |

### Examples

```bash
# List the root of a registered collection
exsh ls mydata

# List a subdirectory
exsh ls mydata:reports/2025

# Sort by modification time, newest first
exsh ls mydata:reports/2025 --sort time --reverse

# Pipe only filenames into another command
exsh ls mydata:reports/2025 --names-only | xargs -I{} exsh cat mydata:reports/2025/{}

# Pipe into grep
exsh ls mydata:reports/2025 | grep ".xml"
```

---

## cat

Print the content of a document to stdout.

```
exsh cat <nick>:<path> [--raw]
```

By default `cat` refuses to print binary content and shows an error. Use `--raw` to write raw bytes to stdout instead.

### Options

| Flag | Description |
|------|-------------|
| `--raw` | Write raw bytes to stdout regardless of MIME type |

### Examples

```bash
# Print an XML document
exsh cat mydata:reports/2025/summary.xml

# Pipe into xmllint
exsh cat mydata:reports/2025/summary.xml | xmllint --format -

# Download a binary to a file
exsh cat --raw mydata:images/logo.png > logo.png
```

---

## put

Upload a local file (or stdin) to a collection path.

```
exsh put <nick>:<path> [-f FILE] [--mime MIME]
```

If the target document already exists it is silently overwritten. The MIME type is guessed from the file extension when not specified; it falls back to `application/xml`.

Before uploading, `exsh` checks that the content is well-formed XML whenever the resolved MIME type is an XML type (`application/xml`, `text/xml`, or any type ending in `+xml`). If the check fails, the upload is refused and the parse error is printed. Non-XML MIME types (e.g. `image/png`, `application/json`) are uploaded without any validation.

### Options

| Flag | Description |
|------|-------------|
| `-f / --file FILE` | Local file to upload. When omitted, stdin is read. |
| `--mime MIME` | Explicit MIME type. Overrides guessed value. |

### Examples

```bash
# Upload a file
exsh put mydata:reports/2025/report.xml -f report.xml

# Upload from stdin
cat report.xml | exsh put mydata:reports/2025/report.xml

# Override MIME type
exsh put mydata:data/config.json -f config.json --mime application/json

# Upload binary
exsh put mydata:images/logo.png -f logo.png --mime image/png
```

---

## cp

Copy a document between local paths and remote eXist collections. All three directions are supported.

```
exsh cp <source> <target>
```

If the target is an existing local directory, the source filename is appended automatically. If the target path ends with `/`, the source filename is also appended.

### Copy directions

| Source | Target | Effect |
|--------|--------|--------|
| `nick:path` | local path | Download remote document to local file |
| local path | `nick:path` | Upload local file to remote collection |
| `nick:path` | `nick:path` | Copy between two remote locations (may be different servers) |

### Examples

```bash
# Remote to local (into a specific file)
exsh cp mydata:reports/2025/summary.xml ./summary.xml

# Remote to local (into a directory — filename preserved)
exsh cp mydata:reports/2025/summary.xml ./downloads/

# Local to remote
exsh cp ./report.xml mydata:reports/2025/report.xml

# Remote to remote (same or different servers)
exsh cp mydata:reports/2025/summary.xml archive:reports/2025/summary.xml
```

---

## edit

Download a document, open it in your editor, and automatically re-upload if the content changed.

```
exsh edit <nick>:<path>
```

The editor is resolved from the `$VISUAL` environment variable, then `$EDITOR`, falling back to `vi`. If you use VS Code, set `EDITOR="code --wait"`.

If the file is not modified, `exsh` prints `No changes.` and exits without uploading.

For XML documents, the content is checked for well-formedness before uploading. If the check fails, `exsh` prints the parse error, prompts you to press Enter, and re-opens the editor so you can fix the problem in place. Quitting the editor without making further changes aborts the upload.

### Examples

```bash
# Edit with whatever $EDITOR is set to
exsh edit mydata:reports/2025/summary.xml

# Temporarily override the editor
EDITOR=nano exsh edit mydata:config.xml
```

---

## rm

Delete one or more documents from an eXist collection.

```
exsh rm <nick>:<path>...
```

Multiple paths can be supplied in a single invocation. Deletion is permanent — there is no undo.

### Examples

```bash
# Delete a single document
exsh rm mydata:reports/2025/old.xml

# Delete multiple documents at once
exsh rm mydata:reports/2025/a.xml mydata:reports/2025/b.xml
```

---

## mkdir

Create a subcollection inside a registered collection.

```
exsh mkdir <nick>:<path>
```

Parent collections must already exist. Use multiple `mkdir` calls to create nested paths.

### Examples

```bash
# Create a subcollection
exsh mkdir mydata:reports/2026

# Create a nested path (parents must exist first)
exsh mkdir mydata:reports
exsh mkdir mydata:reports/2026
exsh mkdir mydata:reports/2026/q1
```

---

## sync

Synchronise a local directory tree and a remote collection, transferring only changed files.

See the dedicated [sync page](sync.md) for full details.

```
exsh sync <source> <dest> [--force] [--fail-fast] [--dry-run] [--delete] [--verbose]
```

Direction is inferred from argument order: local-first means push, remote-first means pull.

### Options

| Flag | Description |
|------|-------------|
| `--force / -f` | Transfer all files, bypassing conflict detection |
| `--fail-fast` | Stop on the first conflict or XML validation failure; manifest is saved so the run can resume (push only) |
| `--dry-run / -n` | Show what would happen without transferring anything |
| `--delete` | Remove files on the destination that no longer exist on the source |
| `--verbose / -v` | Also print unchanged (skipped) files |

### Quick examples

```bash
# Push local folder to server
exsh sync ./reports mydata:reports

# Pull remote collection to local folder
exsh sync mydata:reports ./reports

# Preview a push without doing anything
exsh sync --dry-run ./reports mydata:reports

# Push and delete server-side extras
exsh sync --delete ./reports mydata:reports

# Push but stop immediately if any XML file is malformed
exsh sync --fail-fast ./reports mydata:reports
```

---

## exec

Execute an XQuery script on an eXist-db server and print the result to stdout.

```
exsh exec <nick>[:<path>] [-f FILE] [--no-fix] [--no-validate] [--validator NAME]
```

The query is read from `--file` or from stdin. Before sending, `exsh` optionally preprocesses the source and validates it locally:

**Preprocessing** (enabled by default, skip with `--no-fix`):

- Adds `xquery version "3.1";` if no version declaration is present.
- Adds the `functx` module import if `functx:` functions are referenced but not declared.

**Local validation** (enabled when a supported validator is installed, skip with `--no-validate`):

The first installed validator found on `PATH` is used automatically. Use `--validator` to choose a specific one. Supported validators:

| Name | Tool |
|------|------|
| `basex` | [BaseX](https://basex.org) |
| `saxon` | [Saxon](https://www.saxonica.com) (requires a `saxon` wrapper script on PATH) |

Run `exsh exec --list-validators` to see which validators are available on the current machine.

### Options

| Flag | Description |
|------|-------------|
| `-f / --file FILE` | XQuery file to execute. When omitted, stdin is read. |
| `--no-fix` | Skip preprocessing (version declaration, namespace imports). |
| `--no-validate` | Skip local validation even if a validator is installed. |
| `--validator NAME` | Use a specific local validator by name. |
| `--list-validators` | List known validators and their install status, then exit. |

### Examples

```bash
# Execute a query file against the root of a collection
exsh exec mydata:/ -f query.xq

# Execute from stdin
echo 'count(collection("/db/mydata"))' | exsh exec mydata:/

# Pipe the result into xmllint for pretty-printing
exsh exec mydata:/ -f query.xq | xmllint --format -

# Execute in the context of a subcollection
exsh exec mydata:reports/2025 -f summary.xq

# Skip preprocessing and validation (e.g. for already-complete scripts)
exsh exec mydata:/ --no-fix --no-validate -f query.xq

# Force a specific validator
exsh exec mydata:/ --validator basex -f query.xq

# Check which validators are available locally
exsh exec --list-validators
```

---

## user

Manage user accounts on an eXist-db server.

### user ls

List all user accounts and their group memberships.

```
exsh user ls [--server NICK]
```

Output has one line per user with two tab-separated columns: username and comma-separated group list.

#### Options

| Flag | Description |
|------|-------------|
| `--server NICK` | Server to query. Auto-selected when only one server is configured. |

#### Examples

```bash
# List all users on the only configured server
exsh user ls

# List users on a specific server
exsh user ls --server localhost
```

---

### user add

Create a new user account on the server.

```
exsh user add <username> [--group GROUPS] [--password PASSWORD] [--server NICK]
```

Prompts for a password when `--password` is not supplied so the credential is never written to shell history. The first group in the comma-separated list becomes the primary group.

#### Options

| Flag | Description |
|------|-------------|
| `--group GROUPS` | Comma-separated group names. The first is the primary group. Defaults to `guest`. |
| `--password PASSWORD` | Plaintext password. Prompted interactively when omitted. |
| `--server NICK` | Server to target. Auto-selected when only one server is configured. |

#### Examples

```bash
# Create a user, prompt for password
exsh user add alice --group editors

# Create a user with an explicit password and multiple groups
exsh user add alice --group editors,users --password s3cr3t

# Create a user on a specific server
exsh user add alice --server prod --group editors
```

---

### user rm

Remove a user account from the server.

```
exsh user rm <username> [--yes] [--server NICK]
```

Prompts for confirmation unless `--yes` is supplied.

#### Options

| Flag | Description |
|------|-------------|
| `--yes / -y` | Skip the confirmation prompt. |
| `--server NICK` | Server to target. Auto-selected when only one server is configured. |

#### Examples

```bash
# Remove a user interactively
exsh user rm alice

# Remove without confirmation (e.g. in a script)
exsh user rm alice --yes
```

---

### user info

Show detailed information about a user account.

```
exsh user info <username> [--server NICK]
```

Prints username, full name (when set), group memberships, and enabled status.

#### Options

| Flag | Description |
|------|-------------|
| `--server NICK` | Server to query. Auto-selected when only one server is configured. |

#### Examples

```bash
# Inspect the admin account
exsh user info admin

# Inspect a user on a specific server
exsh user info alice --server prod
```

---

### user passwd

Change a user's password on the server.

```
exsh user passwd <username[@server]> [--stdin] [--server NICK]
```

Prompts for the new password interactively (with confirmation) unless `--stdin` is supplied. The password is never accepted directly on the command line to avoid shell history exposure.

#### Options

| Flag | Description |
|------|-------------|
| `--stdin` | Read the new password from stdin — useful for scripting and pipelines. |
| `--server NICK` | Server to target. Auto-selected when only one server is configured. |

#### Examples

```bash
# Change password interactively (prompted with confirmation)
exsh user passwd alice

# Change password from stdin (for scripting)
echo 'newpassword' | exsh user passwd alice --stdin

# Using @server syntax
exsh user passwd alice@prod --stdin
```

---

## mv

Move or rename a document or collection on the server.

```
exsh mv <source> <target>
```

Both `<source>` and `<target>` must be remote paths (`nick:path`). Local paths are not accepted — use `cp` + `rm` for local↔remote operations.

If `<target>` ends with a trailing `/`, the source name is preserved and the item is moved *into* that collection. Without a trailing slash, the source is moved *and* renamed to the target path in one step.

Moving a collection recursively copies all its contents to the destination, then deletes the source — the source is left intact if any upload fails.

Cross-server moves are not supported; both paths must resolve to the same server. Use `cp` + `rm` for cross-server transfers.

### Examples

```bash
# Rename a document
exsh mv mydata:reports/old.xml mydata:reports/new.xml

# Move a document into a subcollection (filename preserved)
exsh mv mydata:reports/draft.xml mydata:archive/

# Move and rename in one step
exsh mv mydata:reports/draft.xml mydata:archive/final.xml

# Rename a collection
exsh mv mydata:drafts mydata:archive

# Move a collection into another collection (trailing slash)
exsh mv mydata:drafts "mydata:archive/"
```

---

## group

Manage groups on an eXist-db server.

### group ls

List all groups and their members.

```
exsh group ls [@server] [--server NICK]
```

Output has one line per group with two tab-separated columns: group name and comma-separated member list.

The server may be specified as a positional `@nick` argument or via `--server`. When only one server is configured it is selected automatically.

#### Options

| Flag | Description |
|------|-------------|
| `--server NICK` | Server to query. Auto-selected when only one server is configured. |

#### Examples

```bash
# List all groups on the only configured server
exsh group ls

# List groups on a specific server
exsh group ls --server localhost

# Using @server syntax
exsh group ls @prod
```

---

### group add

Create a new group on the server.

```
exsh group add <groupname[@server]> [--server NICK]
```

#### Options

| Flag | Description |
|------|-------------|
| `--server NICK` | Server to target. Auto-selected when only one server is configured. |

#### Examples

```bash
# Create a group
exsh group add editors

# Create a group on a specific server
exsh group add editors --server prod

# Using @server syntax
exsh group add editors@prod
```

---

### group rm

Remove a group from the server.

```
exsh group rm <groupname[@server]> [--yes] [--server NICK]
```

Prompts for confirmation unless `--yes` is supplied.

#### Options

| Flag | Description |
|------|-------------|
| `--yes / -y` | Skip the confirmation prompt. |
| `--server NICK` | Server to target. Auto-selected when only one server is configured. |

#### Examples

```bash
# Remove a group interactively
exsh group rm editors

# Remove without confirmation (e.g. in a script)
exsh group rm editors --yes

# Using @server syntax
exsh group rm editors@prod --yes
```

---

## chown

Change the owner and/or group of a remote document or collection.

```
exsh chown <spec> <nick>:<path> [--recursive]
```

The `<spec>` argument follows Unix `chown` conventions:

| Form | Effect |
|------|--------|
| `owner` | Change the owner only |
| `:group` | Change the group only |
| `owner:group` | Change both owner and group |

At least one of owner or group must be specified. The named user and group are validated against the server before the change is applied — if either does not exist, the command exits with an error and no change is made.

For tab completion, prefix the spec with a server nick to pin a specific server:
`prod@alice:editors`. The prefix is used only for completion and is discarded before the ownership change is applied.

### Options

| Flag | Description |
|------|-------------|
| `--recursive / -R` | Apply the ownership change to the collection and all its contents recursively. Only valid when the target is a collection. |

### Examples

```bash
# Change owner only
exsh chown alice mydata:reports/annual.xml

# Change group only
exsh chown :editors mydata:drafts/

# Change both owner and group
exsh chown alice:editors mydata:reports/annual.xml

# Change the root collection itself (non-recursive)
exsh chown admin mydata:

# Recursively reassign an entire collection tree
exsh chown -R alice mydata:reports
```

---

## chmod

Change the POSIX permissions of a remote document or collection.

```
exsh chmod <mode> <nick>:<path> [--recursive]
```

The `<mode>` argument accepts both octal and symbolic Unix `chmod` notation:

**Octal mode** — a 1–4 digit octal number, with or without a leading `0`:

| Example | Effect |
|---------|--------|
| `0644` | Owner read/write; group and other read-only |
| `0755` | Owner read/write/execute; group and other read/execute |
| `644` | Same as `0644` |

**Symbolic mode** — one or more comma-separated clauses of the form `[ugoa]*[+-=][rwxst]*`:

| Who | Meaning |
|-----|---------|
| `u` | User (owner) |
| `g` | Group |
| `o` | Other |
| `a` | All (equivalent to `ugo`; default when no who is given) |

| Operator | Meaning |
|----------|---------|
| `+` | Add the specified permissions |
| `-` | Remove the specified permissions |
| `=` | Set permissions exactly (clears unspecified bits for the given who) |

| Permission | Meaning |
|------------|---------|
| `r` | Read |
| `w` | Write |
| `x` | Execute |
| `s` | Set-user-ID / set-group-ID bit |
| `t` | Sticky bit |

For symbolic modes the server is queried for the current permissions before applying the change. With `--recursive` each item in the tree is queried and updated independently.

### Options

| Flag | Description |
|------|-------------|
| `--recursive / -R` | Apply the permission change to the collection and all its contents recursively. Only valid when the target is a collection. |

### Examples

```bash
# Set a document to owner read/write, everyone else read-only
exsh chmod 0644 mydata:reports/annual.xml

# Set a collection to rwxr-xr-x
exsh chmod 0755 mydata:reports

# Add execute permission for the owner
exsh chmod u+x mydata:scripts/run.xq

# Remove write permission for group and other
exsh chmod go-w mydata:reports/annual.xml

# Set all to read/write (clears execute bits)
exsh chmod a=rw mydata:reports/annual.xml

# Multiple clauses in one call
exsh chmod u+x,go-w mydata:scripts/run.xq

# Recursively set a whole collection to 0644
exsh chmod -R 0644 mydata:data

# Recursively add user execute to a collection tree
exsh chmod -R u+x mydata:scripts
```
