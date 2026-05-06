import httpx
import pytest

from exist_shell.client import ExistClient
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError
from exist_shell.models import CollectionEntry, ResourceEntry


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


def test_list_collection_parses_subcollection(httpx_mock, a_server, subcollection_xml):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", text=subcollection_xml)
    with ExistClient(a_server) as client:
        items = client.list_collection("/db/myapp")
    assert len(items) == 1
    assert isinstance(items[0], CollectionEntry)
    assert items[0].name == "subdir"
    assert items[0].owner == "admin"
    assert items[0].permissions == "rwxr-xr-x"


def test_list_collection_parses_resource(httpx_mock, a_server, resource_xml):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", text=resource_xml)
    with ExistClient(a_server) as client:
        items = client.list_collection("/db/myapp")
    assert len(items) == 1
    assert isinstance(items[0], ResourceEntry)
    assert items[0].name == "file.xml"
    assert items[0].size == 1234
    assert items[0].mime_type == "application/xml"


def test_list_collection_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", status_code=404)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError) as exc_info:
            client.list_collection("/db/myapp")
    assert exc_info.value.status_code == 404


def test_list_collection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.list_collection("/db/myapp")


def test_list_collection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.list_collection("/db/myapp")


def test_put_document_succeeds_on_201(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="PUT", status_code=201)
    with ExistClient(a_server) as client:
        client.put_document("/db/myapp/doc.xml", b"<root/>", "application/xml")


def test_put_document_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="PUT", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.put_document("/db/myapp/doc.xml", b"<root/>", "application/xml")


def test_put_document_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="PUT", status_code=404)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.put_document("/db/myapp/doc.xml", b"<root/>", "application/xml")


def test_put_document_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.put_document("/db/myapp/doc.xml", b"<root/>", "application/xml")
