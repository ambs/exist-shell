"""Permissions mixin — ownership operations."""

from exist_shell.client._queries import QueryMixin
from exist_shell.utils import xq_escape


class PermissionMixin(QueryMixin):
    """Mixin providing ownership operations against the eXist REST API."""

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
