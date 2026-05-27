"""Permissions mixin — ownership and mode operations."""

import xml.etree.ElementTree as ET

from exist_shell.client._queries import QueryMixin
from exist_shell.utils import xq_escape


def _mode_str_to_int(mode_str: str) -> int:
    """Convert a POSIX mode string to an integer mode value.

    Handles 9-character strings (``"rwxr-xr-x"``) as well as 10-character
    strings with a leading type character (``"drwxr-xr-x"``).  Special bits
    (setuid ``s/S``, setgid ``s/S``, sticky ``t/T``) are decoded correctly.

    Args:
        mode_str: Mode string to convert.

    Returns:
        Integer mode value (0–0o7777).
    """
    if len(mode_str) >= 10:
        mode_str = mode_str[1:]
    if len(mode_str) < 9:
        return 0
    mode_str = mode_str[:9]
    value = 0
    # user
    if mode_str[0] == "r":
        value |= 0o400
    if mode_str[1] == "w":
        value |= 0o200
    if mode_str[2] in ("x", "s"):
        value |= 0o100
    if mode_str[2] in ("s", "S"):
        value |= 0o4000
    # group
    if mode_str[3] == "r":
        value |= 0o040
    if mode_str[4] == "w":
        value |= 0o020
    if mode_str[5] in ("x", "s"):
        value |= 0o010
    if mode_str[5] in ("s", "S"):
        value |= 0o2000
    # other
    if mode_str[6] == "r":
        value |= 0o004
    if mode_str[7] == "w":
        value |= 0o002
    if mode_str[8] in ("x", "t"):
        value |= 0o001
    if mode_str[8] in ("t", "T"):
        value |= 0o1000
    return value


def _int_to_mode_str(mode: int) -> str:
    """Convert an integer mode value to a 9-character POSIX mode string.

    Args:
        mode: Integer mode value (0–0o7777).

    Returns:
        9-character string like ``"rwxr-xr-x"``.
    """
    chars: list[str] = []
    # user
    chars.append("r" if mode & 0o400 else "-")
    chars.append("w" if mode & 0o200 else "-")
    if mode & 0o4000:
        chars.append("s" if mode & 0o100 else "S")
    else:
        chars.append("x" if mode & 0o100 else "-")
    # group
    chars.append("r" if mode & 0o040 else "-")
    chars.append("w" if mode & 0o020 else "-")
    if mode & 0o2000:
        chars.append("s" if mode & 0o010 else "S")
    else:
        chars.append("x" if mode & 0o010 else "-")
    # other
    chars.append("r" if mode & 0o004 else "-")
    chars.append("w" if mode & 0o002 else "-")
    if mode & 0o1000:
        chars.append("t" if mode & 0o001 else "T")
    else:
        chars.append("x" if mode & 0o001 else "-")
    return "".join(chars)


class PermissionMixin(QueryMixin):
    """Mixin providing ownership and mode operations against the eXist REST API."""

    def chown_resource(self, path: str, owner: str | None, group: str | None) -> None:
        """Change the owner and/or group of a document or collection.

        Validates that the specified owner and group exist on the server before
        applying the change, in a single round-trip.  Either ``owner`` or
        ``group`` (or both) must be non-``None``.

        Args:
            path: Full eXist path starting with ``/db/``.
            owner: New owner username, or ``None`` to leave unchanged.
            group: New group name, or ``None`` to leave unchanged.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the user or group does not exist, the path is
                not found, permission is denied, or the query otherwise fails.
        """
        safe_path = xq_escape(path)
        validation: list[str] = []
        changes: list[str] = []

        if owner:
            s = xq_escape(owner)
            validation.append(
                f'if (not(sm:user-exists("{s}"))) then error((), "User not found: {s}") else ()'
            )
            changes.append(f'sm:chown(xs:anyURI("{safe_path}"), "{s}")')

        if group:
            s = xq_escape(group)
            validation.append(
                f'if (not(sm:group-exists("{s}"))) then error((), "Group not found: {s}") else ()'
            )
            changes.append(f'sm:chgrp(xs:anyURI("{safe_path}"), "{s}")')

        clauses = validation + changes
        query = 'xquery version "3.1"; (' + ", ".join(clauses) + ", ())"
        self.execute_query(query)

    def get_permissions(self, path: str) -> int:
        """Return the POSIX mode bits for a document or collection as an integer.

        Args:
            path: Full eXist path starting with ``/db/``.

        Returns:
            Integer mode value (0–0o7777).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the path does not exist or the query fails.
        """
        safe_path = xq_escape(path)
        query = f'xquery version "3.1"; sm:get-permissions(xs:anyURI("{safe_path}"))'
        raw = self.execute_query(query)
        el = ET.fromstring(raw)
        mode_str = el.get("mode", "---------")
        return _mode_str_to_int(mode_str)

    def chmod_resource(self, path: str, mode: int) -> None:
        """Change the POSIX mode of a document or collection.

        Args:
            path: Full eXist path starting with ``/db/``.
            mode: New mode as an integer (0–0o7777).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the path does not exist, permission is denied,
                or the query otherwise fails.
        """
        safe_path = xq_escape(path)
        mode_str = _int_to_mode_str(mode)
        query = f'xquery version "3.1"; sm:chmod(xs:anyURI("{safe_path}"), "{mode_str}")'
        self.execute_query(query)
