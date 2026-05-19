"""Pydantic models for eXist-db REST API responses."""

from typing import NamedTuple

from pydantic import BaseModel


class CollectionEntry(BaseModel):
    """A subcollection entry returned by the eXist-db REST API."""

    name: str
    created: str | None = None
    owner: str | None = None
    group: str | None = None
    permissions: str | None = None


class ResourceEntry(BaseModel):
    """A document resource entry returned by the eXist-db REST API."""

    name: str
    created: str | None = None
    last_modified: str | None = None
    owner: str | None = None
    group: str | None = None
    permissions: str | None = None
    size: int | None = None
    mime_type: str | None = None


CollectionItem = CollectionEntry | ResourceEntry


class DocumentResult(NamedTuple):
    """A retrieved document's raw content and declared MIME type."""

    content: bytes
    mime_type: str


class UserEntry(BaseModel):
    """A user entry with username and groups."""

    username: str
    groups: list[str]


class UserInfo(BaseModel):
    """Detailed user account information."""

    username: str
    full_name: str | None = None
    groups: list[str] = []
    enabled: bool = True
