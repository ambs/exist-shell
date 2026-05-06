"""HTTP client for the eXist-db REST API."""

import xml.etree.ElementTree as ET

import httpx

from exist_shell.config import Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.models import CollectionEntry, CollectionItem, DocumentResult, ResourceEntry

_EXIST_NS = "http://exist.sourceforge.net/NS/exist"


class ExistClient:
    """HTTP client scoped to a single eXist-db server.

    Args:
        server: The server configuration to connect to.
        timeout: Request timeout in seconds.
    """

    def __init__(self, server: Server, timeout: float = 30.0) -> None:
        """Initialize the client and open an HTTP connection."""
        self._base = f"http://{server.host}:{server.port}/exist"
        self._http = httpx.Client(
            auth=(server.user, server.password.get_secret_value()),
            timeout=timeout,
        )

    def check_connection(self) -> None:
        """Verify connectivity and credentials against the server.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
        """
        url = f"{self._base}/rest/db"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        r.raise_for_status()

    def collection_exists(self, name: str) -> bool:
        """Check whether a top-level collection exists under /db/.

        Args:
            name: Collection name (without the /db/ prefix).

        Returns:
            True if the collection exists, False if 404.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
        """
        url = f"{self._base}/rest/db/{name}"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        return r.status_code in (200, 207)

    def list_collection(self, path: str) -> list[CollectionItem]:
        """List subcollections and resources at the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/sub).

        Returns:
            Ordered list of CollectionEntry and ResourceEntry objects.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
        """
        url = f"{self._base}/rest{path}"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        col = root.find(f"{{{_EXIST_NS}}}collection")
        items: list[CollectionItem] = []
        if col is not None:
            for el in col.findall(f"{{{_EXIST_NS}}}subcollection"):
                items.append(CollectionEntry(
                    name=el.get("name", ""),
                    created=el.get("created"),
                    owner=el.get("owner"),
                    group=el.get("group"),
                    permissions=el.get("permissions"),
                ))
            for el in col.findall(f"{{{_EXIST_NS}}}resource"):
                items.append(ResourceEntry(
                    name=el.get("name", ""),
                    created=el.get("created"),
                    last_modified=el.get("last-modified"),
                    owner=el.get("owner"),
                    group=el.get("group"),
                    permissions=el.get("permissions"),
                    size=int(el.get("size", 0)) or None,
                    mime_type=el.get("mime-type"),
                ))
        return items

    def get_document(self, path: str) -> DocumentResult:
        """Retrieve a document's raw bytes and declared MIME type.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/doc.xml).

        Returns:
            DocumentResult with the raw content bytes and MIME type string.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
        """
        url = f"{self._base}/rest{path}"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()
        mime_type = r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return DocumentResult(content=r.content, mime_type=mime_type)

    def put_document(self, path: str, content: bytes, mime_type: str) -> None:
        """Store a document at the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/doc.xml).
            content: Raw document bytes.
            mime_type: MIME type sent as the Content-Type header.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the parent collection does not exist.
        """
        url = f"{self._base}/rest{path}"
        try:
            r = self._http.put(url, content=content, headers={"Content-Type": mime_type})
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> "ExistClient":
        """Enter the context manager."""
        return self

    def __exit__(self, *_) -> None:
        """Exit the context manager and close the connection."""
        self.close()
