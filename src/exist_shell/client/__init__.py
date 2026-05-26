"""HTTP client for the eXist-db REST API."""

from exist_shell.client._collections import CollectionMixin
from exist_shell.client._documents import DocumentMixin
from exist_shell.client._groups import GroupMixin
from exist_shell.client._permissions import PermissionMixin
from exist_shell.client._users import UserMixin


class ExistClient(CollectionMixin, DocumentMixin, UserMixin, GroupMixin, PermissionMixin):
    """HTTP client scoped to a single eXist-db server.

    Args:
        server: The server configuration to connect to.
        timeout: Request timeout in seconds.
    """


__all__ = ["ExistClient"]
