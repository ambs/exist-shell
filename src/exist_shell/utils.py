"""Shared utilities for exist-shell commands."""

from contextlib import contextmanager
from collections.abc import Generator

import typer

from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError


def validate_path(path: str) -> None:
    """Reject paths that contain traversal sequences or null bytes.

    Args:
        path: The eXist path to validate (e.g. /subdir/doc.xml).

    Raises:
        ValueError: If the path contains ``..``, ``.``, or null bytes.
    """
    if "\x00" in path:
        raise ValueError("path contains null bytes")
    for segment in path.split("/"):
        if segment in ("..", "."):
            raise ValueError(f"path traversal not allowed: '{segment}' segment")


def parse_target(target: str, *, path_required: bool = True) -> tuple[str, str]:
    """Parse and validate a ``<nick>:<path>`` target argument.

    Args:
        target: Raw argument string from the CLI (e.g. ``myapp:/docs/file.xml``).
        path_required: If True, exit with an error when no path is given.
            If False, default the path to ``/`` (used by ``ls``).

    Returns:
        Tuple of ``(nick, normalized_path)`` where path starts with ``/``.
    """
    nick, _, path = target.partition(":")
    if not path:
        if path_required:
            typer.echo("Error: path is required (use <nick>:<path>).", err=True)
            raise typer.Exit(1)
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    try:
        validate_path(path)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    return nick, path


def resolve_collection(nick: str, path: str) -> tuple[Collection, Server, str]:
    """Look up a collection by nick and compute the full eXist path.

    Args:
        nick: The collection nickname from the CLI argument.
        path: The validated path component (starts with ``/``).

    Returns:
        Tuple of ``(collection, server, full_path)`` where ``full_path``
        starts with ``/db/``.
    """
    config = Config.load()
    if nick not in config.collections:
        typer.echo(f"Error: collection '{nick}' not found.", err=True)
        raise typer.Exit(1)
    collection = config.collections[nick]
    server = config.servers[collection.server_nick]
    full_path = f"/db/{collection.name}{path}"
    return collection, server, full_path


@contextmanager
def handle_exist_errors(path: str, nick: str, server_nick: str) -> Generator[None, None, None]:
    """Context manager that catches eXist client errors and exits cleanly.

    Args:
        path: The path being accessed (used in error messages).
        nick: The collection nick (used in error messages).
        server_nick: The server nick (used in authentication error messages).
    """
    try:
        yield
    except ExistNotFoundError:
        typer.echo(f"Error: path '{path}' not found in collection '{nick}'.", err=True)
        raise typer.Exit(1)
    except ExistAuthError:
        typer.echo(f"Error: authentication failed for server '{server_nick}'.", err=True)
        raise typer.Exit(1)
    except ExistConnectionError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
