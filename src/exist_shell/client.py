"""HTTP client for the eXist-db REST API."""

import xml.etree.ElementTree as ET
from urllib.parse import quote

import httpx

from exist_shell.config import Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistQueryError
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
        url = self._url(f"/db/{name}")
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
        url = self._url(path)
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()
        items: list[CollectionItem] = []
        root = ET.fromstring(r.text)
        col = root.find(f"{{{_EXIST_NS}}}collection")
        if col is not None:
            for el in col.findall(f"{{{_EXIST_NS}}}collection"):
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
        url = self._url(path)
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
        url = self._url(path)
        try:
            r = self._http.put(url, content=content, headers={"Content-Type": mime_type})
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()

    def create_collection(self, path: str) -> None:
        """Create a collection at the given eXist path.

        Intermediate collections are created automatically if they do not exist.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/newcoll).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the collection cannot be created.
        """
        clean = path.rstrip("/")
        # fold-left walks each path segment from /db downward, threading the
        # parent path as the accumulator. xmldb:create-collection is idempotent
        # (existing collections return their path without error), so intermediate
        # levels are created only when missing. [1] keeps the path string and
        # discards the create-collection return value from the sequence.
        query = (
            'xquery version "3.1"; '
            f'let $parts := tokenize("{clean}", "/")[. != ""] '
            "let $_ := fold-left(tail($parts), \"/\" || head($parts), function($parent, $seg) { "
            "  let $new := $parent || \"/\" || $seg "
            "  return ($new, xmldb:create-collection($parent, $seg))[1] "
            "}) "
            "return ()"
        )
        try:
            self.execute_query(query, context="/db")
        except ExistQueryError:
            raise ExistNotFoundError(path)

    def delete_document(self, path: str) -> None:
        """Delete a document at the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/doc.xml).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
        """
        url = self._url(path)
        try:
            r = self._http.delete(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()

    def delete_collection(self, path: str) -> None:
        """Delete an empty collection at the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/subcol).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
        """
        url = self._url(path)
        try:
            r = self._http.delete(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()

    def execute_query(self, query: str, context: str = "/db") -> str:
        """Execute an XQuery string and return the raw response body.

        Args:
            query: XQuery source code to execute.
            context: The eXist collection path used as the query context.

        Returns:
            Raw response text from the server.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the server returns HTTP 400 or 500 (query error).
        """
        url = self._url(context)
        try:
            r = self._http.post(url, data={"_query": query, "_wrap": "no"})
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code in (400, 500):
            raise ExistQueryError(r.text.strip())
        r.raise_for_status()
        return r.text

    def close(self) -> None:
        """Close the underlying HTTP connection."""
        self._http.close()

    def __enter__(self) -> "ExistClient":
        """Enter the context manager."""
        return self

    def __exit__(self, *_) -> None:
        """Exit the context manager and close the connection."""
        self.close()
