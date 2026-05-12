import importlib
import importlib.util
import sys
import types

import pytest
from pydantic import SecretStr, ValidationError

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


@pytest.mark.parametrize("nick", ["foo", "my-db", "db_1", "A", "a1", "abc-def_123"])
def test_valid_server_nick(nick):
    s = Server(nick=nick, host="localhost")
    assert s.nick == nick


@pytest.mark.parametrize("nick", ["fo o", "f:oo", "/foo", "-foo", "", "foo!", "foo.bar", "_foo"])
def test_invalid_server_nick_raises(nick):
    with pytest.raises(ValidationError):
        Server(nick=nick, host="localhost")


@pytest.mark.parametrize("nick", ["foo", "my-db", "db_1"])
def test_valid_collection_nick(nick):
    c = Collection(nick=nick, server_nick="local", name="mydb")
    assert c.nick == nick


@pytest.mark.parametrize("nick", ["fo o", "f:oo", "-foo", "", "foo!", "_foo"])
def test_invalid_collection_nick_raises(nick):
    with pytest.raises(ValidationError):
        Collection(nick=nick, server_nick="local", name="mydb")


def test_app_state_set_config_path(tmp_path):
    from exist_shell.config import _AppState

    state = _AppState()
    p = tmp_path / "custom.toml"
    state.set_config_path(p)
    assert state.config_path() == p


def test_app_state_config_path_uses_exsh_config_env(monkeypatch, tmp_path):
    from exist_shell.config import _AppState

    state = _AppState()
    p = tmp_path / "env.toml"
    monkeypatch.setenv("EXSH_CONFIG", str(p))
    assert state.config_path() == p


def test_app_state_config_path_falls_back_to_default(monkeypatch):
    from exist_shell.config import _AppState, _DEFAULT_CONFIG_PATH

    state = _AppState()
    monkeypatch.delenv("EXSH_CONFIG", raising=False)
    assert state.config_path() == _DEFAULT_CONFIG_PATH


def test_save_persists_cache_dir(config_path, tmp_path):
    cache = tmp_path / "mycache"
    config = Config(cache_dir=cache)
    config.save()
    reloaded = Config.load()
    assert reloaded.cache_dir == cache


def test_windows_default_paths_use_platformdirs(monkeypatch):
    from pathlib import Path

    fake_platformdirs = types.SimpleNamespace(
        user_config_dir=lambda app, appauthor=None: f"/fake/config/{app}",
        user_cache_dir=lambda app, appauthor=None: f"/fake/cache/{app}",
    )
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setitem(sys.modules, "platformdirs", fake_platformdirs)

    # Load a fresh copy under a throwaway name so exist_shell.config is unaffected.
    spec = importlib.util.spec_from_file_location(
        "_test_config_win32",
        Path(__file__).parent.parent / "src/exist_shell/config.py",
    )
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)

    assert fresh._DEFAULT_CONFIG_PATH == Path("/fake/config/exsh") / "config.toml"
    assert fresh._DEFAULT_CACHE_DIR == Path("/fake/cache/exsh")
