"""Users mixin — user account operations."""

import xml.etree.ElementTree as ET

from exist_shell.client._queries import QueryMixin
from exist_shell.models import UserEntry, UserInfo
from exist_shell.utils import xq_escape


class UserMixin(QueryMixin):
    """Mixin providing user account operations against the eXist REST API."""

    def list_users(self) -> list[UserEntry]:
        """List all user accounts and their group memberships.

        Returns:
            List of UserEntry objects sorted alphabetically by username.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the XQuery fails.
        """
        query = (
            'xquery version "3.1"; '
            '<users>{ '
            'for $u in sm:list-users() '
            'let $groups := sm:get-user-groups($u) '
            'order by $u '
            'return <user name="{$u}" groups="{string-join($groups, ",")}"/> '
            '}</users>'
        )
        raw = self.execute_query(query)
        root = ET.fromstring(raw)
        result: list[UserEntry] = []
        for el in root.findall("user"):
            groups_str = el.get("groups", "")
            groups = [g for g in groups_str.split(",") if g]
            result.append(UserEntry(username=el.get("name", ""), groups=groups))
        return result

    def get_user(self, username: str) -> UserInfo:
        """Get detailed information about a single user account.

        Args:
            username: The account name to look up.

        Returns:
            UserInfo with the account's username, full name, group memberships,
            and whether the account is enabled.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the user does not exist or the query fails.
        """
        safe = xq_escape(username)
        query = (
            'xquery version "3.1"; '
            f'if (not(sm:user-exists("{safe}"))) '
            f'then error((), "User not found: {safe}") '
            f'else '
            f'let $groups := sm:get-user-groups("{safe}") '
            f'let $enabled := sm:is-account-enabled("{safe}") '
            f'let $fullname := (sm:get-account-metadata("{safe}", xs:anyURI("http://axschema.org/namePerson")), "")[1] '
            f'return <user '
            f'name="{safe}" '
            f'fullname="{{$fullname}}" '
            f'enabled="{{$enabled}}" '
            f'groups="{{string-join($groups, \',\')}}" />'
        )
        raw = self.execute_query(query)
        el = ET.fromstring(raw)
        groups_str = el.get("groups", "")
        groups = [g for g in groups_str.split(",") if g]
        return UserInfo(
            username=el.get("name", username),
            full_name=el.get("fullname") or None,
            groups=groups,
            enabled=(el.get("enabled", "true").lower() == "true"),
        )

    def create_user(self, username: str, password: str, groups: list[str]) -> None:
        """Create a new user account.

        The first entry in groups becomes the primary group.

        Args:
            username: The new account name.
            password: The plaintext password.
            groups: One or more group names; the first is the primary group.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the account already exists or the query fails.
        """
        safe_user = xq_escape(username)
        safe_pass = xq_escape(password)
        groups_xq = ", ".join(f'"{xq_escape(g)}"' for g in groups)
        query = (
            'xquery version "3.1"; '
            f'sm:create-account("{safe_user}", "{safe_pass}", ({groups_xq}))'
        )
        self.execute_query(query)

    def delete_user(self, username: str) -> None:
        """Remove a user account from the server.

        Args:
            username: The account name to remove.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the user does not exist or the query fails.
        """
        safe = xq_escape(username)
        query = f'xquery version "3.1"; sm:remove-account("{safe}")'
        self.execute_query(query)

    def change_password(self, username: str, password: str) -> None:
        """Change the password of an existing user account.

        Args:
            username: The account name.
            password: The new plaintext password.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the user does not exist or the query fails.
        """
        safe_user = xq_escape(username)
        safe_pass = xq_escape(password)
        query = (
            'xquery version "3.1"; '
            f'sm:passwd("{safe_user}", "{safe_pass}")'
        )
        self.execute_query(query)
