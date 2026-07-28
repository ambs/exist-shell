"""Shared utilities for exist-shell commands."""

import mimetypes
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path

import typer

from exist_shell.config import Collection, Config, Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistError, ExistNotFoundError


def echo_tty(message: str) -> None:
    """Print a message only when stdout is a TTY.

    Used for interactive heads-up lines that would pollute piped or
    scripted output.

    Args:
        message: The message to print.
    """
    if sys.stdout.isatty():
        typer.echo(message)


def xq_escape(value: str) -> str:
    """Escape a string for safe embedding in an XQuery double-quoted string literal.

    Doubles every ``"`` character so the value can be placed directly
    between XQuery double-quote delimiters without ending the literal early,
    and escapes ``&`` to ``&amp;`` since XQuery string literals parse entity
    references — a raw ``&`` not starting a valid entity/character reference
    is a query parse error.

    Args:
        value: The raw string to embed in an XQuery double-quoted string.

    Returns:
        The string with every ``&`` and double-quote character escaped.
    """
    return value.replace("&", "&amp;").replace('"', '""')


def is_remote(target: str) -> bool:
    r"""Return True if target uses the ``nick:path`` remote syntax.

    A bare ``:`` is ambiguous with local paths: Windows drive letters
    (``C:\data``) and POSIX filenames containing a colon. The prefix before
    the first ``:`` is treated as local rather than a nick when it matches a
    Windows drive letter followed by a path separator, or when it contains a
    path separator itself (meaning it can't be a bare nick). A prefix that
    matches a configured collection nick always wins, and anything else
    falls back to remote so typo'd nicks still get a helpful error.

    Args:
        target: Raw argument string from the CLI.

    Returns:
        True if the string should be interpreted as ``nick:path``.
    """
    if ":" not in target:
        return False
    prefix, _, rest = target.partition(":")
    if prefix in Config.load().collections:
        return True
    if len(prefix) == 1 and prefix.isalpha() and rest.startswith(("\\", "/")):
        return False
    if "/" in prefix or "\\" in prefix:
        return False
    return True


def parse_user_at_server(value: str) -> tuple[str, str | None]:
    """Split a ``user@server`` argument into a (username, server_nick) pair.

    Args:
        value: Raw argument from the CLI, e.g. ``alice@prod``, ``alice``, or ``@prod``.

    Returns:
        A tuple ``(username, server_nick)`` where ``server_nick`` is ``None``
        if no ``@`` suffix was present, and ``username`` is empty for bare
        ``@server`` forms.
    """
    if "@" in value:
        username, _, server = value.rpartition("@")
        return username, server if server else None
    return value, None


def guess_mime(path: Path, default: str = "application/octet-stream") -> str:
    """Guess the MIME type of a file from its extension.

    Args:
        path: Local file path.
        default: MIME type to return when the extension is unknown.

    Returns:
        Guessed MIME type string, or ``default`` if the extension is unrecognised.
    """
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or default


def check_xml_wellformed(content: bytes, mime: str) -> str | None:
    """Return an error message if content is malformed XML, or None if valid or not XML.

    Only inspects content when the MIME type is an XML type (``application/xml``,
    ``text/xml``, or any type ending in ``+xml``).

    Args:
        content: Raw bytes to check.
        mime: MIME type of the content.

    Returns:
        None if the content passes the check or is not an XML MIME type; an
        error message string if the XML is malformed.
    """
    if mime != "application/xml" and mime != "text/xml" and not mime.endswith("+xml"):
        return None
    try:
        ET.fromstring(content)
    except ET.ParseError as e:
        return str(e)
    return None


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
    except ExistError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
