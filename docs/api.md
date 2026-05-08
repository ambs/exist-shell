# Python API — ExistClient

`ExistClient` is the HTTP façade used by all `exsh` commands. You can import it directly to drive eXist-db programmatically from Python.

## Installation

```bash
pip install git+https://github.com/ambs/exist-shell
# or with uv
uv add git+https://github.com/ambs/exist-shell
```

## Quick example

```python
from exist_shell.client import ExistClient
from exist_shell.config import Server

server = Server(
    host="localhost",
    port=8080,
    user="admin",
    password="secret",  # or use SecretStr from pydantic
)

with ExistClient(server) as client:
    client.check_connection()

    items = client.list_collection("/db/myapp")
    for item in items:
        print(item.name)

    result = client.get_document("/db/myapp/config.xml")
    print(result.content.decode())
```

## ExistClient

```python
class ExistClient:
    def __init__(self, server: Server, timeout: float = 30.0) -> None: ...
```

Constructor opens an `httpx.Client` scoped to the given server. Use it as a context manager so the connection is properly closed.

### Methods

#### check_connection

```python
def check_connection(self) -> None
```

Verify connectivity and credentials against the server.

**Raises:**

- `ExistConnectionError` — network-level failure (DNS, refused connection, etc.)
- `ExistAuthError` — server returned HTTP 401

---

#### collection_exists

```python
def collection_exists(self, name: str) -> bool
```

Check whether a top-level collection exists under `/db/`.

**Args:**

- `name` — collection name without the `/db/` prefix (e.g. `"myapp"`)

**Returns:** `True` if the collection exists, `False` if 404.

---

#### list_collection

```python
def list_collection(self, path: str) -> list[CollectionItem]
```

List subcollections and resources at the given eXist path.

**Args:**

- `path` — full eXist path starting with `/db/` (e.g. `"/db/myapp/reports"`)

**Returns:** Ordered list of [`CollectionEntry`](#collectionentry) and [`ResourceEntry`](#resourceentry) objects.

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError`

---

#### get_document

```python
def get_document(self, path: str) -> DocumentResult
```

Retrieve a document's raw bytes and declared MIME type.

**Args:**

- `path` — full eXist path (e.g. `"/db/myapp/config.xml"`)

**Returns:** [`DocumentResult`](#documentresult) named tuple with `content: bytes` and `mime_type: str`.

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError`

---

#### put_document

```python
def put_document(self, path: str, content: bytes, mime_type: str) -> None
```

Store (create or overwrite) a document at the given eXist path.

**Args:**

- `path` — full eXist path (e.g. `"/db/myapp/config.xml"`)
- `content` — raw document bytes
- `mime_type` — MIME type sent as the `Content-Type` header

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError` (parent collection missing)

---

#### create_collection

```python
def create_collection(self, path: str) -> None
```

Create a collection at the given eXist path.

**Args:**

- `path` — full eXist path (e.g. `"/db/myapp/newcoll"`)

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError` (parent missing)

---

#### delete_document

```python
def delete_document(self, path: str) -> None
```

Delete a document at the given eXist path.

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError`

---

#### delete_collection

```python
def delete_collection(self, path: str) -> None
```

Delete a collection at the given eXist path. The collection must be empty.

**Raises:** `ExistConnectionError`, `ExistAuthError`, `ExistNotFoundError`

---

#### close

```python
def close(self) -> None
```

Close the underlying HTTP connection. Called automatically when used as a context manager.

---

## Data models

### CollectionEntry

```python
class CollectionEntry(BaseModel):
    name: str
    created: str | None
    owner: str | None
    group: str | None
    permissions: str | None
```

A subcollection entry returned by [`list_collection`](#list_collection).

---

### ResourceEntry

```python
class ResourceEntry(BaseModel):
    name: str
    created: str | None
    last_modified: str | None
    owner: str | None
    group: str | None
    permissions: str | None
    size: int | None
    mime_type: str | None
```

A document resource entry returned by [`list_collection`](#list_collection).

---

### DocumentResult

```python
class DocumentResult(NamedTuple):
    content: bytes
    mime_type: str
```

The return value of [`get_document`](#get_document).

---

## Exceptions

All exceptions inherit from `ExistError(Exception)`.

| Exception | When raised | Attributes |
|-----------|------------|------------|
| `ExistConnectionError` | Network-level failure (DNS, refused, timeout) | `url`, `cause` |
| `ExistAuthError` | Server returned HTTP 401 | `url` |
| `ExistNotFoundError` | Server returned HTTP 404 | `path` |

```python
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError

try:
    result = client.get_document("/db/myapp/missing.xml")
except ExistNotFoundError as e:
    print(f"Not found: {e.path}")
except ExistAuthError as e:
    print(f"Auth failed: {e.url}")
except ExistConnectionError as e:
    print(f"Cannot connect: {e.cause}")
```
