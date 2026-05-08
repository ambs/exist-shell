# Development

## Setup

```bash
git clone https://github.com/ambs/exist-shell
cd exist-shell
uv sync
```

This installs all runtime and dev dependencies (pytest, ruff, ty, etc.) into `.venv/`.

Verify the install:

```bash
.venv/bin/exsh --help
```

Or activate the environment:

```bash
source .venv/bin/activate
exsh --help
```

## Running checks

```bash
make checks   # ruff lint + ty type-check + pytest
make test     # tests only
make ruff     # lint only
make ty       # type-check only
```

## Project structure

```
src/exist_shell/
  main.py          # Typer app, global callback, subcommand registration
  client.py        # ExistClient — thin httpx wrapper over the eXist REST API
  completions.py   # Dynamic shell completion (hits the server at tab time)
  config.py        # Config model and ~/.config/exsh/config.toml I/O
  models.py        # Pydantic models for REST responses
  exceptions.py    # ExistError hierarchy
  cache.py         # Completion cache helpers
  utils.py         # Shared utilities (MIME guessing, error handling, path parsing)
  commands/        # One module per subcommand
    cat.py
    collection.py
    cp.py
    edit.py
    ls.py
    mkdir.py
    put.py
    rm.py
    server.py
    sync.py
```

## Conventions

- **Python 3.11+** — use builtin generics (`list[str]`, `str | None`) instead of `typing`.
- Every function parameter and return type must be annotated.
- Every public module, class, and method must have a Google-style docstring.
- All REST calls go through `ExistClient`. Commands receive a client via `typer.Context.obj` or instantiate one directly.
- Use `typer.Option(...)` with direct assignment; avoid `Annotated` unless the option is reused across commands.

## Adding a new command

1. Create `src/exist_shell/commands/<name>.py` with a function named after the command.
2. Register it in `main.py` via `app.add_typer()` or `@app.command()`.
3. Add unit tests under `tests/`.
4. Update the command table in `docs/commands.md`.

## Branching and PRs

All changes must go through a pull request — never commit directly to `main`.

1. `git checkout -b feature/<short-description>`
2. Make changes and commit with a signed commit (`git commit -S`).
3. `gh pr create`
4. CI must pass (tests, ruff, ty, e2e) before merging.
