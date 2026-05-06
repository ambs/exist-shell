from pydantic import BaseModel


class CollectionEntry(BaseModel):
    name: str
    created: str | None = None
    owner: str | None = None
    group: str | None = None
    permissions: str | None = None


class ResourceEntry(BaseModel):
    name: str
    created: str | None = None
    last_modified: str | None = None
    owner: str | None = None
    group: str | None = None
    permissions: str | None = None
    size: int | None = None
    mime_type: str | None = None


CollectionItem = CollectionEntry | ResourceEntry
