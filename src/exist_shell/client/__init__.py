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
        connect_timeout: Seconds to wait for the connection to be
            established (and for a connection to free up in the pool).
        read_timeout: Seconds to wait for the server's response body once
            connected.
        write_timeout: Seconds to wait while sending the request body.
    """


__all__ = ["ExistClient"]
