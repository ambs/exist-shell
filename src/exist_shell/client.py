import httpx

from exist_shell.config import Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError


class ExistClient:
    def __init__(self, server: Server, timeout: float = 30.0) -> None:
        self._base = f"http://{server.host}:{server.port}/exist"
        self._http = httpx.Client(
            auth=(server.user, server.password.get_secret_value()),
            timeout=timeout,
        )

    def check_connection(self) -> None:
        url = f"{self._base}/rest/db"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        r.raise_for_status()

    def collection_exists(self, name: str) -> bool:
        url = f"{self._base}/rest/db/{name}"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        return r.status_code in (200, 207)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ExistClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
