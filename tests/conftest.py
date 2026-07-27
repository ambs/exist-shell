"""Shared pytest fixtures for server/collection config and eXist REST responses."""

import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from exist_shell.config import Collection, Config, Server, app_state

_EXIST_NS = "http://exist.sourceforge.net/NS/exist"


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    """Point config persistence at an isolated per-test config.toml."""
    path = tmp_path / "config.toml"
    monkeypatch.setattr(app_state, "_config_path", path)
    return path


@pytest.fixture
def a_server() -> Server:
    """A minimal Server config for a locally-addressed eXist instance."""
    return Server(nick="local", host="localhost", port=8080, user="admin", password=SecretStr(""))


@pytest.fixture
def config_with_collection(config_path, a_server):
    """Persist a config with one server and one collection nick ("myapp")."""
    config = Config.load()
    config.add_server(a_server)
    config.add_collection(Collection(nick="myapp", server_nick="local", name="myapp"))


@pytest.fixture
def subcollection_xml() -> str:
    """Raw eXist REST collection-listing XML containing a single subcollection."""
    return (
        f'<exist:result xmlns:exist="{_EXIST_NS}">'
        '<exist:collection name="/db/myapp">'
        '<exist:collection name="subdir" created="2024-01-01T00:00:00.000"'
        ' owner="admin" group="dba" permissions="rwxr-xr-x"/>'
        "</exist:collection>"
        "</exist:result>"
    )


@pytest.fixture
def resource_xml() -> str:
    """Raw eXist REST collection-listing XML containing a single resource."""
    return (
        f'<exist:result xmlns:exist="{_EXIST_NS}">'
        '<exist:collection name="/db/myapp">'
        '<exist:resource name="file.xml" created="2024-01-01T00:00:00.000"'
        ' last-modified="2024-01-02T00:00:00.000" owner="admin" group="dba"'
        ' permissions="rw-r--r--" size="1234" mime-type="application/xml"/>'
        "</exist:collection>"
        "</exist:result>"
    )


@pytest.fixture
def runner() -> CliRunner:
    """A Typer CliRunner for invoking the exsh app in tests."""
    return CliRunner()
