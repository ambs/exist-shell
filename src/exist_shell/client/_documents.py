"""Documents mixin — document-level operations."""

import base64
from pathlib import PurePosixPath

import httpx

from exist_shell.client._queries import QueryMixin
from exist_shell.exceptions import ExistConnectionError, ExistNotFoundError, ExistQueryError
from exist_shell.models import DocumentResult
from exist_shell.utils import xq_escape

# eXist stores resources with these extensions as binary XQuery modules (MIME type
# application/xquery, per exist-core's mime-types.xml) and executes them on a plain
# GET instead of returning their source bytes.
_EXECUTABLE_EXTENSIONS = {".xq", ".xql", ".xqm", ".xquery", ".xqy", ".xqws"}


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
            ExistServerError: If the server returns any other error status.
        """
        if PurePosixPath(path).suffix.lower() in _EXECUTABLE_EXTENSIONS:
            return self._get_executable_document(path)

        url = self._url(path)
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        self._check_response(r, path)
        mime_type = r.headers.get("content-type", "application/octet-stream").split(";")[0].strip()
        return DocumentResult(content=r.content, mime_type=mime_type)

    def _get_executable_document(self, path: str) -> DocumentResult:
        """Fetch the raw bytes of an executable XQuery resource via an ad-hoc query.

        A plain GET executes these resources instead of returning their source, and
        eXist's REST ``_source=yes`` parameter only works for paths explicitly
        allowlisted server-side in descriptor.xml — which is not the default for
        anything under /db, regardless of the caller's own read permission on the
        resource. ``util:binary-doc`` returns the resource's raw stored bytes and
        only needs the read + query-eval permission the caller already needs to
        execute the resource in the first place.

        Args:
            path: Full eXist path starting with /db/, with an extension in
                ``_EXECUTABLE_EXTENSIONS`` (e.g. /db/myapp/script.xql).

        Returns:
            DocumentResult with the raw content bytes and MIME type application/xquery.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
        """
        safe_path = xq_escape(path)
        query = (
            'xquery version "3.1"; '
            f'let $doc := util:binary-doc("{safe_path}") '
            "return if (exists($doc)) then $doc "
            'else fn:error(xs:QName("exsh:not-found"), "not found")'
        )
        try:
            content = self.execute_query(query)
        except ExistQueryError as e:
            raise ExistNotFoundError(path) from e
        return DocumentResult(content=base64.b64decode(content), mime_type="application/xquery")

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
            ExistServerError: If the server returns any other error status.
        """
        url = self._url(path)
        try:
            r = self._http.put(url, content=content, headers={"Content-Type": mime_type})
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        self._check_response(r, path)

    def delete_document(self, path: str) -> None:
        """Delete a document at the given eXist path.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/doc.xml).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistNotFoundError: If the path does not exist.
            ExistServerError: If the server returns any other error status.
        """
        url = self._url(path)
        try:
            r = self._http.delete(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        self._check_response(r, path)

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
        src_parent_raw = str(src.parent)
        dst_parent_raw = str(dst.parent)
        src_name_raw = src.name
        dst_name_raw = dst.name
        src_parent = xq_escape(src_parent_raw)
        src_name = xq_escape(src_name_raw)
        dst_parent = xq_escape(dst_parent_raw)
        dst_name = xq_escape(dst_name_raw)

        if src_parent_raw == dst_parent_raw:
            query = (
                f'xquery version "3.1"; '
                f'xmldb:rename("{src_parent}", "{src_name}", "{dst_name}")'
            )
        elif src_name_raw == dst_name_raw:
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
