import httpx
import pytest

from exist_shell.client import ExistClient
from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistQueryError
from exist_shell.models import CollectionEntry, DocumentResult, ResourceEntry


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


def test_collection_exists_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.collection_exists("myapp")


def test_get_document_returns_content_and_mime_type(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml",
        content=b"<root/>",
        headers={"content-type": "application/xml; charset=utf-8"},
    )
    with ExistClient(a_server) as client:
        result = client.get_document("/db/myapp/doc.xml")
    assert isinstance(result, DocumentResult)
    assert result.content == b"<root/>"
    assert result.mime_type == "application/xml"


def test_get_document_uses_default_mime_type_when_header_missing(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml",
        content=b"\x00\x01",
    )
    with ExistClient(a_server) as client:
        result = client.get_document("/db/myapp/doc.xml")
    assert result.mime_type == "application/octet-stream"


def test_get_document_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml", status_code=401
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.get_document("/db/myapp/doc.xml")


def test_get_document_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml", status_code=404
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.get_document("/db/myapp/doc.xml")


def test_get_document_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.get_document("/db/myapp/doc.xml")


_PLACEHOLDER = "http://localhost:8080/exist/rest/db/myapp/.keep"
_COLLECTION = "http://localhost:8080/exist/rest/db/myapp"


def test_create_collection_succeeds(httpx_mock, a_server):
    httpx_mock.add_response(url=_PLACEHOLDER, method="PUT", status_code=201)
    httpx_mock.add_response(url=_PLACEHOLDER, method="DELETE", status_code=200)
    with ExistClient(a_server) as client:
        client.create_collection("/db/myapp")


def test_create_collection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url=_PLACEHOLDER, method="PUT", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.create_collection("/db/myapp")


def test_create_collection_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(url=_PLACEHOLDER, method="PUT", status_code=404)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.create_collection("/db/myapp")


def test_create_collection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.create_collection("/db/myapp")


def test_create_collection_suppresses_delete_failure(httpx_mock, a_server):
    httpx_mock.add_response(url=_PLACEHOLDER, method="PUT", status_code=201)
    httpx_mock.add_exception(httpx.ConnectError("refused"), url=_PLACEHOLDER, method="DELETE")
    with ExistClient(a_server) as client:
        client.create_collection("/db/myapp")


def test_delete_document_succeeds(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="DELETE", status_code=200
    )
    with ExistClient(a_server) as client:
        client.delete_document("/db/myapp/doc.xml")


def test_delete_document_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="DELETE", status_code=401
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.delete_document("/db/myapp/doc.xml")


def test_delete_document_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp/doc.xml", method="DELETE", status_code=404
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.delete_document("/db/myapp/doc.xml")


def test_delete_document_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.delete_document("/db/myapp/doc.xml")


def test_delete_collection_succeeds(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp", method="DELETE", status_code=200
    )
    with ExistClient(a_server) as client:
        client.delete_collection("/db/myapp")


def test_delete_collection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp", method="DELETE", status_code=401
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.delete_collection("/db/myapp")


def test_delete_collection_raises_not_found_on_404(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp", method="DELETE", status_code=404
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.delete_collection("/db/myapp")


def test_delete_collection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.delete_collection("/db/myapp")


# ---------------------------------------------------------------------------
# execute_query
# ---------------------------------------------------------------------------

def test_execute_query_returns_text_on_200(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db",
        method="POST",
        text="<result>42</result>",
    )
    with ExistClient(a_server) as client:
        output = client.execute_query("1 + 1")
    assert output == "<result>42</result>"


def test_execute_query_uses_custom_context(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db/myapp",
        method="POST",
        text="ok",
    )
    with ExistClient(a_server) as client:
        output = client.execute_query("1 + 1", context="/db/myapp")
    assert output == "ok"


def test_execute_query_raises_query_error_on_400(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db",
        method="POST",
        status_code=400,
        text="Unexpected token at line 1",
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError) as exc_info:
            client.execute_query("invalid !!!")
    assert "Unexpected token" in str(exc_info.value)


def test_execute_query_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db",
        method="POST",
        status_code=500,
        text="Internal server error",
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.execute_query("1 + 1")


def test_execute_query_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db",
        method="POST",
        status_code=401,
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.execute_query("1 + 1")


def test_execute_query_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.execute_query("1 + 1")
