# Configuration

`exsh` stores its configuration at `~/.config/exsh/config.toml`. You do not need to edit this file manually — the `server` and `collection` subcommands manage it for you.

## Servers

### Add a server

```bash
exsh server add <host> [--port PORT] [--user USER] [--nick NICK]
```

`exsh` will prompt for the password and store it in the config.

```bash
exsh server add localhost --port 8080 --user admin
```

By default, the nickname is derived from the hostname (e.g. `localhost`). Override with `--nick`:

```bash
exsh server add 192.168.1.10 --port 8080 --user admin --nick myserver
```

### List servers

```bash
exsh server ls
```

### Rename a server

Rename a server's nick. All collections registered against it are updated automatically — no collections are lost and no re-registration is needed.

```bash
exsh server rename <old-nick> <new-nick>
```

Example:

```bash
exsh server rename localhost prod
# Server 'localhost' renamed to 'prod'.
# (any collections pointing to 'localhost' now point to 'prod')
```

### Remove a server

Removing a server also removes all collections registered against it.

```bash
exsh server rm <nick>
```

## Collections

A *collection* in `exsh` is a shortcut: a nickname that maps to a `/db/<path>` on a specific server. You never need to type the full path or server URL again.

### Register an existing collection

```bash
exsh collection add <name>[@<server>]
```

If you have a single server registered, `@server` is optional.

```bash
exsh collection add mydata@localhost
```

This registers `/db/mydata` on the `localhost` server under the nick `mydata`. Use `--nick` to choose a different nickname:

```bash
exsh collection add mydata@localhost --nick md
```

### Create and register a new collection

```bash
exsh collection new <name>[@<server>]
```

This creates `/db/<name>` on the server **and** registers it in one step. If the collection already exists, it prints a message and exits without modifying the config.

```bash
exsh collection new reports@localhost
exsh collection new reports@localhost --nick rep
```

### List collections

```bash
exsh collection ls
```

### Remove a collection

```bash
exsh collection rm <nick>
```

This removes the collection from the local config only — it does not delete the data on the server.

## Config file format

The generated `~/.config/exsh/config.toml` looks like this:

```toml
[servers.localhost]
host = "localhost"
port = 8080
user = "admin"
password = "secret"

[collections.mydata]
server = "localhost"
path = "/db/mydata"
```
