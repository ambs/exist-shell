"""Query mixin — XQuery execution."""

import httpx

from exist_shell.client._base import ExistClientBase
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError


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
