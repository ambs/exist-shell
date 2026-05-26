"""Groups mixin — group management operations."""

import xml.etree.ElementTree as ET

from exist_shell.client._queries import QueryMixin
from exist_shell.models import GroupEntry
from exist_shell.utils import xq_escape


class GroupMixin(QueryMixin):
    """Mixin providing group management operations against the eXist REST API."""

    def list_groups(self) -> list[GroupEntry]:
        """List all groups and their members.

        Returns:
            List of GroupEntry objects sorted alphabetically by group name.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the XQuery fails.
        """
        query = (
            'xquery version "3.1"; '
            '<groups>{ '
            'for $g in sm:list-groups() '
            'let $members := sm:get-group-members($g) '
            'order by $g '
            'return <group name="{$g}" members="{string-join($members, ",")}"/> '
            '}</groups>'
        )
        raw = self.execute_query(query)
        root = ET.fromstring(raw)
        result: list[GroupEntry] = []
        for el in root.findall("group"):
            members_str = el.get("members", "")
            members = [m for m in members_str.split(",") if m]
            result.append(GroupEntry(name=el.get("name", ""), members=members))
        return result

    def group_exists(self, groupname: str) -> bool:
        """Check whether a group exists on the server.

        Args:
            groupname: The group name to check.

        Returns:
            True if the group exists, False otherwise.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the query fails.
        """
        safe = xq_escape(groupname)
        query = f'xquery version "3.1"; sm:group-exists("{safe}")'
        return self.execute_query(query).strip() == "true"

    def get_group_members(self, groupname: str) -> list[str]:
        """Return the list of members belonging to a group.

        Args:
            groupname: The group name to look up.

        Returns:
            List of member usernames belonging to the group.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the group does not exist or the query fails.
        """
        safe = xq_escape(groupname)
        query = (
            'xquery version "3.1"; '
            f'if (not(sm:group-exists("{safe}"))) '
            f'then error((), "Group not found: {safe}") '
            f'else '
            f'let $members := sm:get-group-members("{safe}") '
            f'return <members>{{string-join($members, ",")}}</members>'
        )
        raw = self.execute_query(query)
        el = ET.fromstring(raw)
        members_str = el.text or ""
        return [m for m in members_str.split(",") if m]

    def create_group(self, groupname: str) -> None:
        """Create a new group.

        Args:
            groupname: The group name to create.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the group already exists or the query fails.
        """
        safe = xq_escape(groupname)
        query = f'xquery version "3.1"; sm:create-group("{safe}")'
        self.execute_query(query)

    def delete_group(self, groupname: str) -> None:
        """Remove a group from the server.

        Args:
            groupname: The group name to remove.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the group does not exist or the query fails.
        """
        safe = xq_escape(groupname)
        query = f'xquery version "3.1"; sm:remove-group("{safe}")'
        self.execute_query(query)
