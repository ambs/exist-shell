"""Configuration models and persistence for servers and collections."""

from pathlib import Path

import tomlkit
from pydantic import BaseModel, SecretStr

CONFIG_PATH = Path.home() / ".config" / "exist-shell" / "config.toml"


class Server(BaseModel):
    """An eXist-db server configuration."""

    nick: str
    host: str
    port: int = 8080
    user: str = "admin"
    password: SecretStr = SecretStr("")


class Collection(BaseModel):
    """A named collection on an eXist-db server."""

    nick: str
    server_nick: str
    name: str


class Config(BaseModel):
    """Full application configuration holding servers and collections."""

    servers: dict[str, Server] = {}
    collections: dict[str, Collection] = {}

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from disk, returning an empty config if the file is missing.

        Returns:
            The loaded Config instance.
        """
        if not CONFIG_PATH.exists():
            return cls()
        with open(CONFIG_PATH) as f:
            raw = tomlkit.load(f)
        servers = {
            nick: Server(nick=nick, **data)
            for nick, data in raw.get("servers", {}).items()
        }
        collections = {
            nick: Collection(nick=nick, **data)
            for nick, data in raw.get("collections", {}).items()
        }
        return cls(servers=servers, collections=collections)

    def save(self) -> None:
        """Persist the current configuration to disk atomically."""
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        tmp = CONFIG_PATH.with_suffix(".tmp")
        tmp.write_text(tomlkit.dumps(data))
        tmp.rename(CONFIG_PATH)

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
