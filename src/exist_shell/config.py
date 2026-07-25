"""Configuration models and persistence for servers and collections."""

import os
import sys
from pathlib import Path

import tomlkit
from pydantic import BaseModel, Field, SecretStr

# Minimum length 2: a single-character nick could collide with a Windows
# drive letter (e.g. "C:\data") in nick:path parsing (see utils.is_remote).
NICK_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]+$"

if sys.platform == "win32":
    import platformdirs

    _DEFAULT_CONFIG_PATH = Path(platformdirs.user_config_dir("exsh", appauthor=False)) / "config.toml"
    _DEFAULT_CACHE_DIR = Path(platformdirs.user_cache_dir("exsh", appauthor=False))
else:
    _DEFAULT_CONFIG_PATH = Path.home() / ".config" / "exsh" / "config.toml"
    _DEFAULT_CACHE_DIR = Path.home() / ".cache" / "exsh"


class _AppState:
    r"""Process-level singleton that holds the active config file path.

    The path is resolved in this order:
    1. Explicitly set via ``set_config_path()`` (called by the ``--config`` flag).
    2. ``EXSH_CONFIG`` environment variable.
    3. Platform default: XDG (``~/.config/exsh``) on Unix, ``%APPDATA%\exsh`` on Windows.
       XDG Base Directory Specification is a freedesktop.org standard for where
       applications should store config, cache, and data files on Linux/macOS.
    """

    def __init__(self) -> None:
        """Initialise with no explicit path set."""
        self._config_path: Path | None = None

    def set_config_path(self, path: Path) -> None:
        """Override the config file path for this process.

        Args:
            path: Absolute or relative path to the config file.
        """
        self._config_path = path

    def config_path(self) -> Path:
        """Return the resolved config file path.

        Returns:
            Path to the configuration file.
        """
        if self._config_path is not None:
            return self._config_path
        env = os.environ.get("EXSH_CONFIG")
        return Path(env) if env else _DEFAULT_CONFIG_PATH


app_state = _AppState()


class Server(BaseModel):
    """An eXist-db server configuration."""

    nick: str = Field(pattern=NICK_PATTERN)
    host: str
    port: int = 8080
    user: str = "admin"
    password: SecretStr = SecretStr("")


class Collection(BaseModel):
    """A named collection on an eXist-db server."""

    nick: str = Field(pattern=NICK_PATTERN)
    server_nick: str
    name: str


class Config(BaseModel):
    """Full application configuration holding servers and collections."""

    servers: dict[str, Server] = {}
    collections: dict[str, Collection] = {}
    cache_dir: Path | None = None

    def resolved_cache_dir(self) -> Path:
        """Return the active cache root directory.

        Returns:
            ``cache_dir`` from config if set, otherwise ``~/.cache/exsh``.
        """
        return self.cache_dir if self.cache_dir is not None else _DEFAULT_CACHE_DIR

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from disk, returning an empty config if the file is missing.

        Returns:
            The loaded Config instance.
        """
        path = app_state.config_path()
        if not path.exists():
            return cls()
        with open(path) as f:
            raw = tomlkit.load(f)
        servers = {
            nick: Server(nick=nick, **data)
            for nick, data in raw.get("servers", {}).items()
        }
        collections = {
            nick: Collection(nick=nick, **data)
            for nick, data in raw.get("collections", {}).items()
        }
        cache_dir_raw = raw.get("cache_dir")
        cache_dir = Path(cache_dir_raw) if cache_dir_raw else None
        return cls(servers=servers, collections=collections, cache_dir=cache_dir)

    def save(self) -> None:
        """Persist the current configuration to disk atomically."""
        path = app_state.config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {
            "servers": {
                nick: {
                    "host": s.host,
                    "port": s.port,
                    "user": s.user,
                    "password": s.password.get_secret_value(),
                }
                for nick, s in self.servers.items()
            },
            "collections": {
                nick: {
                    "server_nick": c.server_nick,
                    "name": c.name,
                }
                for nick, c in self.collections.items()
            },
        }
        if self.cache_dir is not None:
            data["cache_dir"] = str(self.cache_dir)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(tomlkit.dumps(data))
        tmp.rename(path)

    def add_server(self, server: Server) -> None:
        """Add a server and persist the configuration.

        Args:
            server: The server to add.

        Raises:
            ValueError: If a server with the same nick already exists.
        """
        if server.nick in self.servers:
            raise ValueError(f"Server nick '{server.nick}' already exists.")
        self.servers[server.nick] = server
        self.save()

    def add_collection(self, collection: Collection) -> None:
        """Add a collection and persist the configuration.

        Args:
            collection: The collection to add.

        Raises:
            ValueError: If a collection with the same nick already exists.
        """
        if collection.nick in self.collections:
            raise ValueError(f"Collection nick '{collection.nick}' already exists.")
        self.collections[collection.nick] = collection
        self.save()

    def remove_collection(self, nick: str) -> None:
        """Remove a collection and persist the configuration.

        Args:
            nick: Nickname of the collection to remove.

        Raises:
            KeyError: If no collection with that nick exists.
        """
        del self.collections[nick]
        self.save()

    def remove_server(self, nick: str) -> list[str]:
        """Remove a server and all collections registered on it, then persist.

        Args:
            nick: Nickname of the server to remove.

        Returns:
            List of collection nicks that were removed as a side-effect.

        Raises:
            KeyError: If no server with that nick exists.
        """
        del self.servers[nick]
        cascaded = [c for c, col in self.collections.items() if col.server_nick == nick]
        for c in cascaded:
            del self.collections[c]
        self.save()
        return cascaded

    def rename_server(self, old_nick: str, new_nick: str) -> list[str]:
        """Rename a server nick and update all collection references, then persist.

        Args:
            old_nick: Current nickname of the server.
            new_nick: New nickname for the server.

        Returns:
            List of collection nicks whose server_nick was updated.

        Raises:
            KeyError: If no server with old_nick exists.
            ValueError: If new_nick already exists as a server nick.
        """
        if new_nick in self.servers:
            raise ValueError(f"Server nick '{new_nick}' already exists.")
        server = self.servers[old_nick]
        self.servers[new_nick] = Server(
            nick=new_nick,
            host=server.host,
            port=server.port,
            user=server.user,
            password=server.password,
        )
        del self.servers[old_nick]
        updated = [c for c, col in self.collections.items() if col.server_nick == old_nick]
        for c in updated:
            self.collections[c] = self.collections[c].model_copy(update={"server_nick": new_nick})
        self.save()
        return updated
