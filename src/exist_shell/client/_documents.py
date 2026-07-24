"""Documents mixin — document-level operations."""

from pathlib import PurePosixPath

import httpx

from exist_shell.client._queries import QueryMixin
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistQueryError
from exist_shell.models import DocumentResult


class DocumentMixin(QueryMixin):
    """Mixin providing document-level operations against the eXist REST API."""

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
            # Without _source=yes, eXist executes executable resources (.xql, .xqm) on
            # GET instead of returning their raw bytes.
            r = self._http.get(url, params={"_source": "yes"})
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

    def move_document(self, src_path: str, dst_path: str) -> None:
        """Move or rename a single document using XQuery.

        Selects the most efficient XQuery call based on the relationship
        between source and destination:

        - Same parent → ``xmldb:rename``
        - Different parent, same name → ``xmldb:move``
        - Different parent, different name → ``xmldb:move`` then ``xmldb:rename``

        Args:
            src_path: Full eXist path of the source document.
            dst_path: Full eXist path of the destination document.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the source or destination parent does not exist.
        """
        src = PurePosixPath(src_path.rstrip("/"))
        dst = PurePosixPath(dst_path.rstrip("/"))
        src_parent = str(src.parent)
        src_name = src.name
        dst_parent = str(dst.parent)
        dst_name = dst.name

        if src_parent == dst_parent:
            query = (
                f'xquery version "3.1"; '
                f'xmldb:rename("{src_parent}", "{src_name}", "{dst_name}")'
            )
        elif src_name == dst_name:
            query = (
                f'xquery version "3.1"; '
                f'xmldb:move("{src_parent}", "{dst_parent}", "{src_name}")'
            )
        else:
            query = (
                f'xquery version "3.1"; '
                f'let $_ := xmldb:move("{src_parent}", "{dst_parent}", "{src_name}") '
                f'return xmldb:rename("{dst_parent}", "{src_name}", "{dst_name}")'
            )

        try:
            self.execute_query(query)
        except ExistQueryError as e:
            raise ExistNotFoundError(src_path) from e
