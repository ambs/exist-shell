"""Shared utilities for exist-shell commands."""


def validate_path(path: str) -> None:
    """Reject paths that contain traversal sequences or null bytes.

    Args:
        path: The eXist path to validate (e.g. /subdir/doc.xml).

    Raises:
        ValueError: If the path contains ``..``, ``.``, or null bytes.
    """
    if "\x00" in path:
        raise ValueError("path contains null bytes")
    for segment in path.split("/"):
        if segment in ("..", "."):
            raise ValueError(f"path traversal not allowed: '{segment}' segment")
