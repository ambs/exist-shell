import httpx


class ExistClient:
    def __init__(self, url: str, user: str, password: str, timeout: float = 30.0) -> None:
        self._http = httpx.Client(
            base_url=url,
            auth=(user, password),
            timeout=timeout,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ExistClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
