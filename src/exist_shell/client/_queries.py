"""Query mixin — XQuery execution."""

import httpx

from exist_shell.client._base import ExistClientBase
from exist_shell.exceptions import ExistConnectionError, ExistQueryError
from exist_shell.utils import xq_escape


class QueryMixin(ExistClientBase):
    """Mixin providing XQuery execution against the eXist REST API."""

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
            ExistServerError: If the server returns any other error status.
        """
        url = self._url(context)
        try:
            r = self._http.post(url, data={"_query": query, "_wrap": "no"})
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code in (400, 500):
            raise ExistQueryError(r.text.strip())
        self._check_response(r)
        return r.text

    def find_documents(self, path: str, expression: str) -> list[str]:
        """Find documents under a collection whose content matches an XPath expression.

        The expression is embedded into the generated XQuery without validation
        or escaping, so it can execute arbitrary XQuery. Callers are responsible
        for only passing expressions from a trusted source.

        Args:
            path: Full eXist collection path starting with /db/ to search under.
            expression: XPath expression evaluated recursively under ``path``
                (e.g. ``foo[@type="draft"]``).

        Returns:
            Sorted, de-duplicated list of full document paths (starting with
            /db/) containing at least one match.

        Raises:
            ExistConnectionError: If the server cannot be reached.
            ExistAuthError: If the server returns HTTP 401.
            ExistQueryError: If the expression is invalid or the query fails.
        """
        safe_path = xq_escape(path)
        query = (
            'xquery version "3.1"; '
            "string-join("
            f'for $hit in collection("{safe_path}")//({expression}) '
            "let $doc-uri := document-uri(root($hit)) "
            "group by $doc-uri "
            "order by $doc-uri "
            "return $doc-uri, "
            '"&#10;")'
        )
        raw = self.execute_query(query)
        return [line for line in raw.splitlines() if line.strip()]
