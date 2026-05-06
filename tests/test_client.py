import httpx
import pytest

from exist_shell.client import ExistClient
from exist_shell.exceptions import ExistAuthError, ExistConnectionError


def test_check_connection_succeeds_on_200(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", status_code=200)
    with ExistClient(a_server) as client:
        client.check_connection()


def test_check_connection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError) as exc_info:
            client.check_connection()
    assert exc_info.value.status_code == 401


def test_check_connection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("Connection refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.check_connection()


def test_collection_exists_returns_true_on_200(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", status_code=200)
    with ExistClient(a_server) as client:
        assert client.collection_exists("myapp") is True


def test_collection_exists_returns_false_on_404(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", status_code=404)
    with ExistClient(a_server) as client:
        assert client.collection_exists("myapp") is False


def test_collection_exists_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.collection_exists("myapp")
