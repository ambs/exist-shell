class ExistError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ExistConnectionError(ExistError):
    def __init__(self, url: str, cause: Exception) -> None:
        super().__init__(f"Cannot connect to {url}: {cause}")
        self.url = url
        self.cause = cause


class ExistAuthError(ExistError):
    def __init__(self, url: str) -> None:
        super().__init__(f"Authentication failed for {url}", status_code=401)
        self.url = url
