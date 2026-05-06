from typing import Any


def complete_collection_path(ctx: Any, param: Any, incomplete: str) -> list[str]:
    """Shell completion for eXist collection/document paths."""
    # TODO: use ctx.obj (ExistClient) to list collections matching incomplete
    return []
