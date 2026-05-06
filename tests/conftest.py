import pytest
from pydantic import SecretStr
from typer.testing import CliRunner

from exist_shell.config import Server


@pytest.fixture
def config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr("exist_shell.config.CONFIG_PATH", path)
    return path


@pytest.fixture
def a_server() -> Server:
    return Server(nick="local", host="localhost", port=8080, user="admin", password=SecretStr(""))


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()
