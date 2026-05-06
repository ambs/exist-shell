# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`exsh` — a command-line tool to interact with an eXist-db server via its REST API. Subcommand structure (like git). Designed to work with shell pipes for scripting.

## Dev setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync                        # install all deps including dev group
exsh --help
exsh --version
```

## Commands

```bash
make checks                    # run ruff, ty and tests
make test                      # run tests
make ruff                      # lint with ruff
make ty                        # type-check with ty
```

## Linting

Never run `ruff --fix` across the whole project. Only apply it to a specific file, and only when a manual edit has already failed to resolve the issue.

## Code conventions

- Python 3.11+. Never import from `typing` when a builtin works (`list`, `dict`, `str | None`, etc.).
- Every function parameter and return type must be explicitly annotated.
- Use direct Typer option assignment (`x: bool = typer.Option(...)`) over `Annotated` unless reuse across commands justifies it.
- `ExistClient` is the single HTTP facade — all REST calls go through it. Commands receive a client via `typer.Context.obj`.
- Shell completion for collection/document paths lives in `completions.py`.

## Architecture

```
src/exist_shell/
  main.py        # Typer app, global callback, subcommand registration
  client.py      # ExistClient — thin httpx wrapper over the eXist REST API
  completions.py # Dynamic shell completion functions (hit the server at tab time)
```

Subcommands will be added as modules and registered via `app.add_typer()` or `@app.command()` in `main.py`.
