"""chmod command — change POSIX permissions on a document or collection."""

import re
from collections.abc import Callable

import typer

from exist_shell.client import ExistClient
from exist_shell.completions import collection_target_completer
from exist_shell.models import CollectionEntry
from exist_shell.utils import handle_exist_errors, parse_target, resolve_collection

# ---------------------------------------------------------------------------
# Per-who bit tables used by the symbolic-mode parser
# ---------------------------------------------------------------------------

# Maps (who, perm_char) → the bit to set/clear
_WHO_PERM: dict[str, dict[str, int]] = {
    "u": {"r": 0o400, "w": 0o200, "x": 0o100, "s": 0o4000, "t": 0},
    "g": {"r": 0o040, "w": 0o020, "x": 0o010, "s": 0o2000, "t": 0},
    "o": {"r": 0o004, "w": 0o002, "x": 0o001, "s": 0,       "t": 0o1000},
}

# Bits to clear when applying the '=' operator for a given who
_WHO_CLEAR: dict[str, int] = {
    "u": 0o4700,   # setuid + user rwx
    "g": 0o2070,   # setgid + group rwx
    "o": 0o1007,   # sticky + other rwx
}

# ---------------------------------------------------------------------------
# Mode parsing helpers
# ---------------------------------------------------------------------------

_OCTAL_RE = re.compile(r"0?[0-7]{1,4}$")
_SYMBOLIC_RE = re.compile(r"[ugoa]*[+\-=][rwxst]*(,[ugoa]*[+\-=][rwxst]*)*$")

# Type alias: either a resolved integer mode or a callable that maps the
# current mode (int) to the new mode (int).
_ModeSpec = int | Callable[[int], int]


def _is_octal_mode(mode: str) -> bool:
    """Return ``True`` if *mode* looks like an octal mode string.

    Accepts strings of 1–4 octal digits with an optional leading ``0``
    (e.g. ``"0755"``, ``"644"``, ``"7"``, ``"4755"``).

    Args:
        mode: The mode string from the CLI.

    Returns:
        ``True`` when the string is a valid octal mode.
    """
    return bool(_OCTAL_RE.match(mode))


def _parse_octal_mode(mode: str) -> int:
    """Parse an octal mode string to an integer.

    Args:
        mode: An octal string like ``"0755"`` or ``"644"``.

    Returns:
        Integer mode value (0–0o7777).
    """
    return int(mode, 8)


def _apply_symbolic_mode(mode_str: str, current: int) -> int:
    """Apply a symbolic mode string to a current integer mode.

    Parses a comma-separated list of clauses of the form
    ``[ugoa]*[+-=][rwxst]*``.  An empty *who* prefix is treated as ``a``
    (all).

    Args:
        mode_str: Symbolic mode string (e.g. ``"u+x"``, ``"go-w"``,
            ``"a=rw"``, ``"u+x,go-r"``).
        current: Current mode as an integer.

    Returns:
        New mode as an integer.

    Raises:
        ValueError: If the mode string contains an invalid clause.
    """
    result = current
    for clause in mode_str.split(","):
        m = re.fullmatch(r"([ugoa]*)([+\-=])([rwxst]*)", clause.strip())
        if not m:
            raise ValueError(f"invalid symbolic mode clause: '{clause}'")
        who_str, op, perms_str = m.groups()

        # Empty who or explicit 'a' expands to all three categories.
        whos: list[str] = list(who_str) if (who_str and who_str != "a") else ["u", "g", "o"]

        # Accumulate the bits that change.
        change_bits = 0
        for w in whos:
            for p in perms_str:
                change_bits |= _WHO_PERM[w].get(p, 0)

        if op == "+":
            result |= change_bits
        elif op == "-":
            result &= ~change_bits
        else:  # op == "="
            # Clear all bits belonging to the specified who, then set new ones.
            clear_mask = 0
            for w in whos:
                clear_mask |= _WHO_CLEAR[w]
            result = (result & ~clear_mask) | change_bits

    return result


# ---------------------------------------------------------------------------
# Internal helpers shared by single and recursive apply
# ---------------------------------------------------------------------------


def _resolve_mode(client: ExistClient, path: str, mode_spec: _ModeSpec) -> int:
    """Return the concrete integer mode to apply at *path*.

    For an integer *mode_spec* this is a no-op.  For a callable, it first
    queries the current permissions of *path* and passes them through.

    Args:
        client: Active ExistClient.
        path: Full eXist path to query (only used for symbolic specs).
        mode_spec: Resolved integer or symbolic-mode callable.

    Returns:
        Integer mode to apply.
    """
    if not isinstance(mode_spec, int):
        current = client.get_permissions(path)
        return mode_spec(current)
    return mode_spec


def _chmod_tree(client: ExistClient, path: str, mode_spec: _ModeSpec) -> int:
    """Recursively change permissions of a collection and all its contents.

    For an octal (integer) *mode_spec* the same absolute mode is applied to
    every item.  For a symbolic *mode_spec* the relative change is applied
    independently to each item's current permissions.

    Args:
        client: Active ExistClient.
        path: Full eXist path to the root collection.
        mode_spec: Resolved integer mode or symbolic-mode callable.

    Returns:
        Total number of resources and collections whose mode was changed.
    """
    client.chmod_resource(path, _resolve_mode(client, path, mode_spec))
    count = 1
    for item in client.list_collection(path):
        child = f"{path}/{item.name}"
        if isinstance(item, CollectionEntry):
            count += _chmod_tree(client, child, mode_spec)
        else:
            client.chmod_resource(child, _resolve_mode(client, child, mode_spec))
            count += 1
    return count


# ---------------------------------------------------------------------------
# chmod command
# ---------------------------------------------------------------------------


def chmod(
    mode: str = typer.Argument(
        help=(
            "Permission mode: octal (e.g. '0755', '644') or symbolic "
            "(e.g. 'u+x', 'go-w', 'a=rw', 'u+x,go-r')."
        ),
    ),
    target: str = typer.Argument(
        help="Remote path: <nick>:<path>.",
        autocompletion=collection_target_completer("any"),
    ),
    recursive: bool = typer.Option(
        False, "--recursive", "-R",
        help="Apply recursively to all contents of a collection.",
    ),
) -> None:
    """Change POSIX permissions on a document or collection.

    Accepts both octal (e.g. ``0755``, ``644``) and symbolic (e.g. ``u+x``,
    ``go-w``, ``a=rw``) mode specifications.

    Raises:
        typer.Exit: On invalid mode, unknown collection, or server error.
    """
    # Determine and validate the mode specification.
    mode_spec: _ModeSpec
    if _is_octal_mode(mode):
        mode_spec = _parse_octal_mode(mode)
    elif _SYMBOLIC_RE.match(mode):
        captured = mode
        mode_spec = lambda current, _m=captured: _apply_symbolic_mode(_m, current)
    else:
        typer.echo(
            f"Error: invalid mode '{mode}'. "
            "Use octal (e.g. '0755') or symbolic (e.g. 'u+x', 'go-w').",
            err=True,
        )
        raise typer.Exit(1)

    nick, path = parse_target(target, path_required=False)
    collection, server, full_path = resolve_collection(nick, path)

    with handle_exist_errors(path, nick, collection.server_nick):
        with ExistClient(server) as client:
            if recursive:
                if not client.is_collection(full_path):
                    typer.echo(
                        f"Error: '{path}' is not a collection. "
                        "Omit -R to chmod a single document.",
                        err=True,
                    )
                    raise typer.Exit(1)
                count = _chmod_tree(client, full_path, mode_spec)
                typer.echo(f"Permissions of '{path}' updated ({count} items).")
            else:
                client.chmod_resource(full_path, _resolve_mode(client, full_path, mode_spec))
                typer.echo(f"Permissions of '{path}' updated.")
