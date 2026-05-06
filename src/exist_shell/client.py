import xml.etree.ElementTree as ET

import httpx

from exist_shell.config import Server
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.models import CollectionEntry, CollectionItem, ResourceEntry

_EXIST_NS = "http://exist.sourceforge.net/NS/exist"


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

    def list_collection(self, path: str) -> list[CollectionItem]:
        url = f"{self._base}/rest{path}"
        try:
            r = self._http.get(url)
        except httpx.RequestError as e:
            raise ExistConnectionError(url, e) from e
        if r.status_code == 401:
            raise ExistAuthError(url)
        if r.status_code == 404:
            raise ExistNotFoundError(path)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        col = root.find(f"{{{_EXIST_NS}}}collection")
        items: list[CollectionItem] = []
        if col is not None:
            for el in col.findall(f"{{{_EXIST_NS}}}subcollection"):
                items.append(CollectionEntry(
                    name=el.get("name", ""),
                    created=el.get("created"),
                    owner=el.get("owner"),
                    group=el.get("group"),
                    permissions=el.get("permissions"),
                ))
            for el in col.findall(f"{{{_EXIST_NS}}}resource"):
                items.append(ResourceEntry(
                    name=el.get("name", ""),
                    created=el.get("created"),
                    last_modified=el.get("last-modified"),
                    owner=el.get("owner"),
                    group=el.get("group"),
                    permissions=el.get("permissions"),
                    size=int(el.get("size", 0)) or None,
                    mime_type=el.get("mime-type"),
                ))
        return items

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "ExistClient":
        return self

    def __exit__(self, *_) -> None:
        self.close()
