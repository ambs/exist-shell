# CLI Commands

All commands follow the pattern `exsh <command> [options]`. Paths to remote documents and collections are written as `<nick>:<path>` (e.g. `mydata:reports/2025/summary.xml`), where `<nick>` is the short name you gave to a registered collection.

## ls

List subcollections and documents at a collection path.

```
exsh ls <nick>[:<path>]
```

The output is tab-separated with one entry per line. Subcollections are shown with a trailing `/`.

**Columns for collections:** `name/`, `permissions`, `owner`, `created`

**Columns for resources:** `name`, `permissions`, `owner`, `size (bytes)`, `mime-type`, `last-modified`

### Examples

```bash
# List the root of a registered collection
exsh ls mydata

# List a subdirectory
exsh ls mydata:reports/2025

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
exsh sync <source> <dest> [--force] [--dry-run] [--delete]
```

Direction is inferred from argument order: local-first means push, remote-first means pull.

### Options

| Flag | Description |
|------|-------------|
| `--force / -f` | Transfer all files, bypassing conflict detection |
| `--dry-run / -n` | Show what would happen without transferring anything |
| `--delete` | Remove files on the destination that no longer exist on the source |

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
