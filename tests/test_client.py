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


_PARENT_URL = "http://localhost:8080/exist/rest/db"


def test_create_collection_succeeds(httpx_mock, a_server):
    httpx_mock.add_response(url=_PARENT_URL, method="POST", status_code=200)
    with ExistClient(a_server) as client:
        client.create_collection("/db/myapp")


def test_create_collection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url=_PARENT_URL, method="POST", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.create_collection("/db/myapp")


def test_create_collection_raises_not_found_on_query_error(httpx_mock, a_server):
    httpx_mock.add_response(url=_PARENT_URL, method="POST", status_code=500, text="collection not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.create_collection("/db/myapp")


def test_create_collection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
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


def test_execute_query_read_timeout_message_differs_from_connect_timeout(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ReadTimeout("timed out"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError) as exc_info:
            client.execute_query("1 + 1")
    assert "did not respond in time" in str(exc_info.value)
    assert "Cannot connect" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# is_collection
# ---------------------------------------------------------------------------

def test_is_collection_returns_true(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", text="true")
    with ExistClient(a_server) as client:
        assert client.is_collection("/db/myapp/subcol") is True


def test_is_collection_returns_false_for_document(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", text="false")
    with ExistClient(a_server) as client:
        assert client.is_collection("/db/myapp/doc.xml") is False


def test_is_collection_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.is_collection("/db/myapp/sub")


def test_is_collection_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.is_collection("/db/myapp/sub")


# ---------------------------------------------------------------------------
# move_document
# ---------------------------------------------------------------------------

def test_move_document_same_parent_uses_rename_query(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", text="")
    with ExistClient(a_server) as client:
        client.move_document("/db/myapp/old.xml", "/db/myapp/new.xml")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "xmldb:rename" in body["_query"][0]
    assert "old.xml" in body["_query"][0]
    assert "new.xml" in body["_query"][0]


def test_move_document_different_parent_same_name_uses_move_query(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", text="")
    with ExistClient(a_server) as client:
        client.move_document("/db/myapp/src/doc.xml", "/db/myapp/dst/doc.xml")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "xmldb:move" in body["_query"][0]
    assert "xmldb:rename" not in body["_query"][0]


def test_move_document_different_parent_different_name_uses_move_and_rename(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", text="")
    with ExistClient(a_server) as client:
        client.move_document("/db/myapp/src/old.xml", "/db/myapp/dst/new.xml")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "xmldb:move" in body["_query"][0]
    assert "xmldb:rename" in body["_query"][0]


def test_move_document_raises_not_found_on_query_error(httpx_mock, a_server):
    httpx_mock.add_response(
        url="http://localhost:8080/exist/rest/db", method="POST", status_code=500, text="not found"
    )
    with ExistClient(a_server) as client:
        with pytest.raises(ExistNotFoundError):
            client.move_document("/db/myapp/missing.xml", "/db/myapp/dst.xml")


def test_move_document_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url="http://localhost:8080/exist/rest/db", method="POST", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.move_document("/db/myapp/doc.xml", "/db/myapp/new.xml")


def test_move_document_raises_connection_error_on_network_failure(httpx_mock, a_server):
    httpx_mock.add_exception(httpx.ConnectError("refused"))
    with ExistClient(a_server) as client:
        with pytest.raises(ExistConnectionError):
            client.move_document("/db/myapp/doc.xml", "/db/myapp/new.xml")


# ---------------------------------------------------------------------------
# list_users
# ---------------------------------------------------------------------------

_DB_POST_URL = "http://localhost:8080/exist/rest/db"


def test_list_users_returns_user_entries(httpx_mock, a_server):
    xml = '<users><user name="admin" groups="dba"/><user name="alice" groups="editors,users"/></users>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        users = client.list_users()
    assert len(users) == 2
    assert users[0].username == "admin"
    assert users[0].groups == ["dba"]
    assert users[1].username == "alice"
    assert users[1].groups == ["editors", "users"]


def test_list_users_returns_empty_list(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="<users/>")
    with ExistClient(a_server) as client:
        users = client.list_users()
    assert users == []


def test_list_users_handles_empty_groups(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text='<users><user name="guest" groups=""/></users>')
    with ExistClient(a_server) as client:
        users = client.list_users()
    assert users[0].groups == []


# ---------------------------------------------------------------------------
# user_exists
# ---------------------------------------------------------------------------


def test_user_exists_returns_true(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="true")
    with ExistClient(a_server) as client:
        assert client.user_exists("alice") is True


def test_user_exists_returns_false(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="false")
    with ExistClient(a_server) as client:
        assert client.user_exists("nobody") is False


def test_user_exists_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.user_exists("alice")


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


def test_get_user_returns_user_info(httpx_mock, a_server):
    xml = '<user name="alice" fullname="Alice Smith" enabled="true" groups="editors,users"/>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        info = client.get_user("alice")
    assert info.username == "alice"
    assert info.full_name == "Alice Smith"
    assert info.groups == ["editors", "users"]
    assert info.enabled is True


def test_get_user_handles_empty_full_name(httpx_mock, a_server):
    xml = '<user name="bob" fullname="" enabled="false" groups="guest"/>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        info = client.get_user("bob")
    assert info.full_name is None
    assert info.enabled is False


def test_get_user_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="User not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.get_user("nobody")


# ---------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------


def test_create_user_sends_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.create_user("alice", "s3cr3t", ["editors", "users"])
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:create-account" in body["_query"][0]
    assert "alice" in body["_query"][0]


def test_create_user_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="account exists")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.create_user("alice", "pw", ["guest"])


# ---------------------------------------------------------------------------
# delete_user
# ---------------------------------------------------------------------------


def test_delete_user_sends_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.delete_user("alice")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:remove-account" in body["_query"][0]
    assert "alice" in body["_query"][0]


def test_delete_user_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="account not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.delete_user("nobody")


# ---------------------------------------------------------------------------
# change_password
# ---------------------------------------------------------------------------


def test_change_password_sends_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.change_password("alice", "n3wp4ss")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:passwd" in body["_query"][0]
    assert "alice" in body["_query"][0]


def test_change_password_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="user not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.change_password("nobody", "pw")


# ---------------------------------------------------------------------------
# chown_resource
# ---------------------------------------------------------------------------


def test_chown_resource_owner_only_sends_chown(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.chown_resource("/db/myapp/doc.xml", "alice", None)
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:chown" in body["_query"][0]
    assert "sm:chgrp" not in body["_query"][0]
    assert "sm:user-exists" in body["_query"][0]


def test_chown_resource_group_only_sends_chgrp(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.chown_resource("/db/myapp/doc.xml", None, "editors")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:chgrp" in body["_query"][0]
    assert "sm:chown" not in body["_query"][0]
    assert "sm:group-exists" in body["_query"][0]


def test_chown_resource_both_sends_chown_and_chgrp(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.chown_resource("/db/myapp/doc.xml", "alice", "editors")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:chown" in body["_query"][0]
    assert "sm:chgrp" in body["_query"][0]
    assert "sm:user-exists" in body["_query"][0]
    assert "sm:group-exists" in body["_query"][0]


def test_chown_resource_unknown_user_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="User not found: nobody")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError, match="User not found"):
            client.chown_resource("/db/myapp/doc.xml", "nobody", None)


def test_chown_resource_unknown_group_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="Group not found: ghost")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError, match="Group not found"):
            client.chown_resource("/db/myapp/doc.xml", None, "ghost")


def test_chown_resource_raises_query_error_on_permission_denied(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="Permission denied")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.chown_resource("/db/myapp/doc.xml", "alice", None)


# ---------------------------------------------------------------------------
# group_exists
# ---------------------------------------------------------------------------


def test_group_exists_returns_true(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="true")
    with ExistClient(a_server) as client:
        assert client.group_exists("dba") is True


def test_group_exists_returns_false(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="false")
    with ExistClient(a_server) as client:
        assert client.group_exists("ghost") is False


# ---------------------------------------------------------------------------
# _mode_str_to_int
# ---------------------------------------------------------------------------

from exist_shell.client._permissions import _int_to_mode_str, _mode_str_to_int


def test_mode_str_to_int_rwxr_xr_x():
    assert _mode_str_to_int("rwxr-xr-x") == 0o755


def test_mode_str_to_int_rw_r__r__():
    assert _mode_str_to_int("rw-r--r--") == 0o644


def test_mode_str_to_int_all_dashes():
    assert _mode_str_to_int("---------") == 0


def test_mode_str_to_int_strips_type_prefix():
    # 10-char string with leading 'd' (directory)
    assert _mode_str_to_int("drwxr-xr-x") == 0o755


def test_mode_str_to_int_short_string_returns_zero():
    assert _mode_str_to_int("rwx") == 0


def test_mode_str_to_int_setuid_with_execute():
    # 's' in user position: setuid + execute
    assert _mode_str_to_int("rwsr-xr-x") == 0o4755


def test_mode_str_to_int_setuid_without_execute():
    # 'S' in user position: setuid, no execute
    assert _mode_str_to_int("rwSr-xr-x") == 0o4655


def test_mode_str_to_int_setgid_with_execute():
    # 's' in group position: setgid + execute
    assert _mode_str_to_int("rwxr-sr-x") == 0o2755


def test_mode_str_to_int_setgid_without_execute():
    # 'S' in group position: setgid, no execute
    # 0o2745 = setgid + user(rwx) + group(r--) + other(r-x)
    assert _mode_str_to_int("rwxr-Sr-x") == 0o2745


def test_mode_str_to_int_sticky_with_execute():
    # 't' in other position: sticky + execute
    assert _mode_str_to_int("rwxr-xr-t") == 0o1755


def test_mode_str_to_int_sticky_without_execute():
    # 'T' in other position: sticky, no execute
    assert _mode_str_to_int("rwxr-xr-T") == 0o1754


# ---------------------------------------------------------------------------
# _int_to_mode_str
# ---------------------------------------------------------------------------


def test_int_to_mode_str_0755():
    assert _int_to_mode_str(0o755) == "rwxr-xr-x"


def test_int_to_mode_str_0644():
    assert _int_to_mode_str(0o644) == "rw-r--r--"


def test_int_to_mode_str_zero():
    assert _int_to_mode_str(0) == "---------"


def test_int_to_mode_str_setuid_with_execute():
    assert _int_to_mode_str(0o4755) == "rwsr-xr-x"


def test_int_to_mode_str_setuid_without_execute():
    assert _int_to_mode_str(0o4655) == "rwSr-xr-x"


def test_int_to_mode_str_setgid_with_execute():
    assert _int_to_mode_str(0o2755) == "rwxr-sr-x"


def test_int_to_mode_str_setgid_without_execute():
    # 0o2745 = setgid + user(rwx) + group(r--) + other(r-x) → 'S' in group position
    assert _int_to_mode_str(0o2745) == "rwxr-Sr-x"


def test_int_to_mode_str_sticky_with_execute():
    assert _int_to_mode_str(0o1755) == "rwxr-xr-t"


def test_int_to_mode_str_sticky_without_execute():
    assert _int_to_mode_str(0o1754) == "rwxr-xr-T"


def test_mode_str_round_trips():
    for mode in (0o755, 0o644, 0o000, 0o777, 0o4755, 0o2755, 0o1755):
        assert _mode_str_to_int(_int_to_mode_str(mode)) == mode


# ---------------------------------------------------------------------------
# get_permissions
# ---------------------------------------------------------------------------

_SM_NS = "http://exist-db.org/xquery/securitymanager"


def test_get_permissions_returns_integer_mode(httpx_mock, a_server):
    xml = f'<sm:permission xmlns:sm="{_SM_NS}" owner="admin" group="dba" mode="rwxr-xr-x"/>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        assert client.get_permissions("/db/myapp/doc.xml") == 0o755


def test_get_permissions_handles_missing_mode_attribute(httpx_mock, a_server):
    # When the 'mode' attribute is absent, the default "---------" → 0
    xml = f'<sm:permission xmlns:sm="{_SM_NS}" owner="admin" group="dba"/>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        assert client.get_permissions("/db/myapp/doc.xml") == 0


def test_get_permissions_sends_get_permissions_query(httpx_mock, a_server):
    xml = f'<sm:permission xmlns:sm="{_SM_NS}" owner="admin" group="dba" mode="rw-r--r--"/>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        client.get_permissions("/db/myapp/doc.xml")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:get-permissions" in body["_query"][0]


def test_get_permissions_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="Not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.get_permissions("/db/myapp/missing.xml")


# ---------------------------------------------------------------------------
# chmod_resource
# ---------------------------------------------------------------------------


def test_chmod_resource_sends_chmod_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.chmod_resource("/db/myapp/doc.xml", 0o755)
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:chmod" in body["_query"][0]
    assert "rwxr-xr-x" in body["_query"][0]


def test_chmod_resource_encodes_mode_as_mode_string(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.chmod_resource("/db/myapp/doc.xml", 0o644)
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "rw-r--r--" in body["_query"][0]


def test_chmod_resource_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="Permission denied")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.chmod_resource("/db/myapp/doc.xml", 0o644)


def test_group_exists_raises_auth_error_on_401(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=401)
    with ExistClient(a_server) as client:
        with pytest.raises(ExistAuthError):
            client.group_exists("dba")


# ---------------------------------------------------------------------------
# list_groups
# ---------------------------------------------------------------------------


def test_list_groups_returns_group_entries(httpx_mock, a_server):
    xml = '<groups><group name="dba" members="admin"/><group name="editors" members="alice,bob"/></groups>'
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text=xml)
    with ExistClient(a_server) as client:
        groups = client.list_groups()
    assert len(groups) == 2
    assert groups[0].name == "dba"
    assert groups[0].members == ["admin"]
    assert groups[1].name == "editors"
    assert groups[1].members == ["alice", "bob"]


def test_list_groups_returns_empty_list(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="<groups/>")
    with ExistClient(a_server) as client:
        groups = client.list_groups()
    assert groups == []


def test_list_groups_handles_empty_members(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text='<groups><group name="empty" members=""/></groups>')
    with ExistClient(a_server) as client:
        groups = client.list_groups()
    assert groups[0].members == []


# ---------------------------------------------------------------------------
# get_group_members
# ---------------------------------------------------------------------------


def test_get_group_members_returns_member_list(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="<members>alice,bob</members>")
    with ExistClient(a_server) as client:
        members = client.get_group_members("editors")
    assert members == ["alice", "bob"]


def test_get_group_members_returns_empty_for_no_members(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="<members></members>")
    with ExistClient(a_server) as client:
        members = client.get_group_members("empty")
    assert members == []


def test_get_group_members_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="Group not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.get_group_members("ghost")


# ---------------------------------------------------------------------------
# create_group
# ---------------------------------------------------------------------------


def test_create_group_sends_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.create_group("editors")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:create-group" in body["_query"][0]
    assert "editors" in body["_query"][0]


def test_create_group_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="group exists")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.create_group("editors")


# ---------------------------------------------------------------------------
# delete_group
# ---------------------------------------------------------------------------


def test_delete_group_sends_query(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", text="")
    with ExistClient(a_server) as client:
        client.delete_group("editors")
    from urllib.parse import parse_qs
    body = parse_qs(httpx_mock.get_requests()[0].content.decode())
    assert "sm:remove-group" in body["_query"][0]
    assert "editors" in body["_query"][0]


def test_delete_group_raises_query_error_on_500(httpx_mock, a_server):
    httpx_mock.add_response(url=_DB_POST_URL, method="POST", status_code=500, text="group not found")
    with ExistClient(a_server) as client:
        with pytest.raises(ExistQueryError):
            client.delete_group("ghost")
