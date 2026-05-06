import pytest
from pydantic import SecretStr

from exist_shell.config import Collection, Config, Server


def test_load_returns_empty_config_when_no_file(config_path):
    config = Config.load()
    assert config.servers == {}
    assert config.collections == {}


def test_add_server_persists(config_path, a_server):
    config = Config.load()
    config.add_server(a_server)

    reloaded = Config.load()
    assert "local" in reloaded.servers
    assert reloaded.servers["local"].host == "localhost"


def test_add_server_duplicate_nick_raises(config_path, a_server):
    config = Config.load()
    config.add_server(a_server)
    with pytest.raises(ValueError, match="already exists"):
        config.add_server(a_server)


def test_add_collection_persists(config_path, a_server):
    config = Config.load()
    config.add_server(a_server)
    collection = Collection(nick="myapp", server_nick="local", name="myapp")
    config.add_collection(collection)

    reloaded = Config.load()
    assert "myapp" in reloaded.collections
    assert reloaded.collections["myapp"].server_nick == "local"


def test_add_collection_duplicate_nick_raises(config_path, a_server):
    config = Config.load()
    config.add_server(a_server)
    collection = Collection(nick="myapp", server_nick="local", name="myapp")
    config.add_collection(collection)
    with pytest.raises(ValueError, match="already exists"):
        config.add_collection(collection)


def test_password_not_exposed_in_repr():
    server = Server(nick="s", host="h", password=SecretStr("topsecret"))
    assert "topsecret" not in repr(server)


def test_password_round_trips_through_file(config_path):
    server = Server(nick="s", host="localhost", password=SecretStr("mypass"))
    config = Config.load()
    config.add_server(server)

    reloaded = Config.load()
    assert reloaded.servers["s"].password.get_secret_value() == "mypass"
