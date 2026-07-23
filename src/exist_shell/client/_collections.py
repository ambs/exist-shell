"""Collections mixin — collection-level operations."""

import xml.etree.ElementTree as ET

import httpx

from exist_shell.client._queries import QueryMixin
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistQueryError
from exist_shell.models import CollectionEntry, CollectionItem, ResourceEntry
from exist_shell.utils import xq_escape

_EXIST_NS = "http://exist.sourceforge.net/NS/exist"
DEFAULT_CHILD_NAMES_LIMIT = 200


class CollectionMixin(QueryMixin):
    """Mixin providing collection-level operations against the eXist REST API."""

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

    def list_child_names(
        self, path: str, prefix: str = "", limit: int = DEFAULT_CHILD_NAMES_LIMIT
    ) -> list[CollectionItem]:
        """List child collection and resource names only, skipping metadata.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/sub).
            prefix: When set, only names starting with this string are
                returned. Filtering happens server-side so collections with
                very large child counts don't need their full listing
                serialized and transferred just to be filtered locally.
            limit: Maximum number of names to return. Caps unbounded
                listings (e.g. an empty prefix against a collection with
                tens of thousands of children) so a single tab press can't
                fetch, cache, and pipe an entire collection's worth of names
                into the shell. Callers should treat a result whose length
                equals `limit` as potentially truncated.

        Returns:
            Ordered list of CollectionEntry and ResourceEntry objects with only
            `name` populated — used where full metadata is unneeded (e.g. shell
            completion).

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the query fails.
        """
        safe_path = xq_escape(path)
        safe_prefix = xq_escape(prefix)
        query = (
            'xquery version "3.1"; '
            f'let $c := "{safe_path}" '
            f'let $p := "{safe_prefix}" '
            "let $all := ("
            'for $sub in xmldb:get-child-collections($c)[starts-with(., $p)] return "c:" || $sub, '
            'for $res in xmldb:get-child-resources($c)[starts-with(., $p)] return "r:" || $res'
            ") "
            f'return string-join(subsequence($all, 1, {int(limit)}), "&#10;")'
        )
        raw = self.execute_query(query)
        items: list[CollectionItem] = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            marker, name = line[:2], line[2:]
            if marker == "c:":
                items.append(CollectionEntry(name=name))
            elif marker == "r:":
                items.append(ResourceEntry(name=name))
        return items

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

    def is_collection(self, path: str) -> bool:
        """Return True if path is an existing collection, False if it is a document or absent.

        Args:
            path: Full eXist path starting with /db/ (e.g. /db/myapp/sub).

        Returns:
            True when a collection exists at that path, False otherwise.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
        """
        query = f'xquery version "3.1"; xmldb:collection-available("{path}")'
        result = self.execute_query(query)
        return result.strip() == "true"
