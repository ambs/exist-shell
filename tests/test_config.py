"""Tests for server/collection config persistence in config.py."""

import importlib
import importlib.util
import stat
import sys
import types

import pytest
from pydantic import SecretStr, ValidationError

from exist_shell.config import Collection, Config, Server


def test_load_returns_empty_config_when_no_file(config_path):
    """Load returns empty config when no file."""
    config = Config.load()
    assert config.servers == {}
    assert config.collections == {}


def test_add_server_persists(config_path, a_server):
    """Add server persists."""
    config = Config.load()
    config.add_server(a_server)

    reloaded = Config.load()
    assert "local" in reloaded.servers
    assert reloaded.servers["local"].host == "localhost"


def test_add_server_duplicate_nick_raises(config_path, a_server):
    """Add server duplicate nick raises."""
    config = Config.load()
    config.add_server(a_server)
    with pytest.raises(ValueError, match="already exists"):
        config.add_server(a_server)


def test_add_collection_persists(config_path, a_server):
    """Add collection persists."""
    config = Config.load()
    config.add_server(a_server)
    collection = Collection(nick="myapp", server_nick="local", name="myapp")
    config.add_collection(collection)

    reloaded = Config.load()
    assert "myapp" in reloaded.collections
    assert reloaded.collections["myapp"].server_nick == "local"


def test_add_collection_duplicate_nick_raises(config_path, a_server):
    """Add collection duplicate nick raises."""
    config = Config.load()
    config.add_server(a_server)
    collection = Collection(nick="myapp", server_nick="local", name="myapp")
    config.add_collection(collection)
    with pytest.raises(ValueError, match="already exists"):
        config.add_collection(collection)


def test_password_not_exposed_in_repr():
    """Password not exposed in repr."""
    server = Server(nick="sv", host="h", password=SecretStr("fake-value-123"))
    assert "fake-value-123" not in repr(server)


def test_password_round_trips_through_file(config_path):
    """Password round trips through file."""
    server = Server(nick="sv", host="localhost", password=SecretStr("test-pw"))
    config = Config.load()
    config.add_server(server)

    reloaded = Config.load()
    assert reloaded.servers["sv"].password.get_secret_value() == "test-pw"


@pytest.mark.parametrize("nick", ["foo", "my-db", "db_1", "a1", "abc-def_123"])
def test_valid_server_nick(nick):
    """Valid server nick."""
    s = Server(nick=nick, host="localhost")
    assert s.nick == nick


@pytest.mark.parametrize("nick", ["fo o", "f:oo", "/foo", "-foo", "", "foo!", "foo.bar", "_foo", "A"])
def test_invalid_server_nick_raises(nick):
    """Invalid server nick raises."""
    with pytest.raises(ValidationError):
        Server(nick=nick, host="localhost")


@pytest.mark.parametrize("nick", ["foo", "my-db", "db_1"])
def test_valid_collection_nick(nick):
    """Valid collection nick."""
    c = Collection(nick=nick, server_nick="local", name="mydb")
    assert c.nick == nick


@pytest.mark.parametrize("nick", ["fo o", "f:oo", "-foo", "", "foo!", "_foo", "A"])
def test_invalid_collection_nick_raises(nick):
    """Invalid collection nick raises."""
    with pytest.raises(ValidationError):
        Collection(nick=nick, server_nick="local", name="mydb")


def test_app_state_set_config_path(tmp_path):
    """App state set config path."""
    from exist_shell.config import _AppState

    state = _AppState()
    p = tmp_path / "custom.toml"
    state.set_config_path(p)
    assert state.config_path() == p


def test_app_state_config_path_uses_exsh_config_env(monkeypatch, tmp_path):
    """App state config path uses exsh config env."""
    from exist_shell.config import _AppState

    state = _AppState()
    p = tmp_path / "env.toml"
    monkeypatch.setenv("EXSH_CONFIG", str(p))
    assert state.config_path() == p


def test_app_state_config_path_falls_back_to_default(monkeypatch):
    """App state config path falls back to default."""
    from exist_shell.config import _AppState, _DEFAULT_CONFIG_PATH

    state = _AppState()
    monkeypatch.delenv("EXSH_CONFIG", raising=False)
    assert state.config_path() == _DEFAULT_CONFIG_PATH


def test_save_persists_cache_dir(config_path, tmp_path):
    """Save persists cache dir."""
    cache = tmp_path / "mycache"
    config = Config(cache_dir=cache)
    config.save()
    reloaded = Config.load()
    assert reloaded.cache_dir == cache


# ---------------------------------------------------------------------------
# file permissions (issue #136)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_save_writes_config_file_owner_only(config_path, a_server):
    """Save writes config file owner only."""
    config = Config.load()
    config.add_server(a_server)
    mode = stat.S_IMODE(config_path.stat().st_mode)
    assert mode == 0o600


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_save_writes_config_dir_owner_only(config_path, a_server):
    """Save writes config dir owner only."""
    config = Config.load()
    config.add_server(a_server)
    mode = stat.S_IMODE(config_path.parent.stat().st_mode)
    assert mode == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_save_tightens_preexisting_loose_dir_permissions(config_path, a_server):
    """Save tightens preexisting loose dir permissions."""
    config_path.parent.chmod(0o755)
    config = Config.load()
    config.add_server(a_server)
    mode = stat.S_IMODE(config_path.parent.stat().st_mode)
    assert mode == 0o700


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_load_warns_on_stderr_for_group_readable_file(config_path, a_server, capsys):
    """Load warns on stderr for group readable file."""
    config = Config.load()
    config.add_server(a_server)
    config_path.chmod(0o644)

    Config.load()

    captured = capsys.readouterr()
    assert "readable by other users" in captured.err


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits only")
def test_load_does_not_warn_for_owner_only_file(config_path, a_server, capsys):
    """Load does not warn for owner only file."""
    config = Config.load()
    config.add_server(a_server)

    Config.load()

    captured = capsys.readouterr()
    assert "readable by other users" not in captured.err


def test_windows_default_paths_use_platformdirs(monkeypatch):
    """Windows default paths use platformdirs."""
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
    assert spec is not None
    assert spec.loader is not None
    fresh = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fresh)

    assert fresh._DEFAULT_CONFIG_PATH == Path("/fake/config/exsh") / "config.toml"
    assert fresh._DEFAULT_CACHE_DIR == Path("/fake/cache/exsh")


# ---------------------------------------------------------------------------
# rename_server
# ---------------------------------------------------------------------------


def test_rename_server_updates_key_in_servers(config_path, a_server):
    """Rename server updates key in servers."""
    config = Config.load()
    config.add_server(a_server)
    config.rename_server("local", "prod")
    reloaded = Config.load()
    assert "prod" in reloaded.servers
    assert "local" not in reloaded.servers


def test_rename_server_updates_nick_field(config_path, a_server):
    """Rename server updates nick field."""
    config = Config.load()
    config.add_server(a_server)
    config.rename_server("local", "prod")
    assert Config.load().servers["prod"].nick == "prod"


def test_rename_server_preserves_server_attributes(config_path, a_server):
    """Rename server preserves server attributes."""
    config = Config.load()
    config.add_server(a_server)
    config.rename_server("local", "prod")
    reloaded = Config.load()
    s = reloaded.servers["prod"]
    assert s.host == "localhost"
    assert s.port == 8080
    assert s.user == "admin"


def test_rename_server_updates_collection_server_nick(config_path, a_server):
    """Rename server updates collection server nick."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.rename_server("local", "prod")
    assert Config.load().collections["myapp"].server_nick == "prod"


def test_rename_server_returns_updated_collection_nicks(config_path, a_server):
    """Rename server returns updated collection nicks."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="app1", server_nick="local", name="app1"))
    config.add_collection(Collection(nick="app2", server_nick="local", name="app2"))
    updated = config.rename_server("local", "prod")
    assert set(updated) == {"app1", "app2"}


def test_rename_server_no_collections_returns_empty(config_path, a_server):
    """Rename server no collections returns empty."""
    config = Config.load()
    config.add_server(a_server)
    updated = config.rename_server("local", "prod")
    assert updated == []


def test_rename_server_leaves_other_server_collections_untouched(config_path, a_server):
    """Rename server leaves other server collections untouched."""
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))
    config.add_collection(Collection(nick="prodapp", server_nick="prod", name="prodapp"))
    config.rename_server("local", "staging")
    assert Config.load().collections["prodapp"].server_nick == "prod"


def test_rename_server_duplicate_new_nick_raises(config_path, a_server):
    """Rename server duplicate new nick raises."""
    config = Config.load()
    config.add_server(a_server)
    config.add_server(Server(nick="prod", host="prod.example.com", password=SecretStr("")))
    with pytest.raises(ValueError, match="already exists"):
        config.rename_server("local", "prod")


def test_rename_server_unknown_old_nick_raises(config_path):
    """Rename server unknown old nick raises."""
    config = Config.load()
    with pytest.raises(KeyError):
        config.rename_server("ghost", "newname")
