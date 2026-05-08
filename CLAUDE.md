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

## Branching and pull requests

All changes must go through a pull request — never commit directly to `main`.

1. Create a feature branch: `git checkout -b feature/<short-description>`
2. Make changes, commit with a signed commit (`git commit -S`)
3. Push the branch and open a PR via `gh pr create`
4. Do not merge without the PR being reviewed and all CI checks passing

## File discipline

Never stage or commit files that were not explicitly created as part of the current task or explicitly requested by the user. This includes cache directories, build artifacts, lock files, and any other files that appear as a side effect of running tools.

## Linting

Never run `ruff --fix` across the whole project. Only apply it to a specific file, and only when a manual edit has already failed to resolve the issue.

## Docstrings

Every public module, class, and method must have a docstring. Use Google style:

```python
def my_method(self, path: str) -> list[str]:
    """Short one-line summary.

    Args:
        path: The collection path under /db/.

    Returns:
        List of item names found at the path.

    Raises:
        ExistNotFoundError: If the path does not exist.
        ExistAuthError: If authentication fails.
    """
```

- `Args` section required whenever the method has parameters beyond `self`.
- `Returns` section required whenever the return type is not `None`.
- `Raises` section required whenever the method raises documented exceptions.
- Ruff enforces this via `select = ["D"]` with `convention = "google"`.

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
