"""Custom exceptions for eXist-db REST API errors."""


class ExistError(Exception):
    """Base exception for eXist-db REST API errors.

    Attributes:
        status_code: HTTP status code associated with the error, if any.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        """Initialize with a message and optional HTTP status code."""
        super().__init__(message)
        self.status_code = status_code


class ExistConnectionError(ExistError):
    """Raised when a network-level error prevents reaching the server.

    Attributes:
        url: The URL that could not be reached.
        cause: The underlying transport exception.
    """

    def __init__(self, url: str, cause: Exception) -> None:
        """Initialize with the target URL and the underlying cause."""
        super().__init__(f"Cannot connect to {url}: {cause}")
        self.url = url
        self.cause = cause


class ExistAuthError(ExistError):
    """Raised when the server returns HTTP 401 Unauthorized.

    Attributes:
        url: The URL that rejected the credentials.
    """

    def __init__(self, url: str) -> None:
        """Initialize with the URL that rejected authentication."""
        super().__init__(f"Authentication failed for {url}", status_code=401)
        self.url = url


class ExistNotFoundError(ExistError):
    """Raised when the server returns HTTP 404 Not Found.

    Attributes:
        path: The eXist path that was not found.
    """

    def __init__(self, path: str) -> None:
        """Initialize with the path that was not found."""
        super().__init__(f"Not found: {path}", status_code=404)
        self.path = path
