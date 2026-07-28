"""Base HTTP client — connection setup and low-level helpers."""

from typing import Self
from urllib.parse import quote

import httpx

from exist_shell.config import Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistServerError


class ExistClientBase:
    """Core HTTP plumbing shared by all domain mixins.

    Args:
        server: The server configuration to connect to.
        connect_timeout: Seconds to wait for the connection to be
            established (and for a connection to free up in the pool).
            Kept short so an unreachable host fails fast.
        read_timeout: Seconds to wait for the server's response body once
            connected. Kept longer to accommodate slow-but-legitimate
            queries.
        write_timeout: Seconds to wait while sending the request body
            (e.g. uploading a document).
    """

    def __init__(
        self,
        server: Server,
        connect_timeout: float = 10.0,
        read_timeout: float = 30.0,
        write_timeout: float = 10.0,
    ) -> None:
        """Initialize the client and open an HTTP connection."""
        self._base = server.base_url
        self._http = httpx.Client(
            auth=(server.user, server.password.get_secret_value()),
            timeout=httpx.Timeout(
                connect_timeout,
                read=read_timeout,
                write=write_timeout,
                pool=connect_timeout,
            ),
        )

    def _url(self, path: str) -> str:
        """Build a percent-encoded REST URL for the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/doc.xml).

        Returns:
            Absolute URL safe to pass to httpx.
        """
        return f"{self._base}/rest{quote(path, safe='/')}"

    def check_connection(self) -> None:
        """Verify connectivity and credentials against the server.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistServerError: If the server returns any other error status.
        """
        url = f"{self._base}/rest/db"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        self._check_response(r)

    def _check_response(self, r: httpx.Response, path: str | None = None) -> None:
        """Raise a typed exception for a non-2xx eXist REST response.

        Args:
            r: The HTTP response to check.
            path: The eXist path being accessed, used in the 404 message.
                Falls back to the request URL when not given.

        Raises:
            ExistAuthError: If the response status is 401.
            ExistNotFoundError: If the response status is 404.
            ExistServerError: For any other non-2xx status.
        """
        if r.status_code == 401:
            raise ExistAuthError(str(r.request.url))
        if r.status_code == 404:
            raise ExistNotFoundError(path if path is not None else str(r.request.url))
        if r.is_error:
            raise ExistServerError(r.status_code, r.text.strip())

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *_: object) -> None:
        """Exit the context manager and close the connection."""
        self.close()
