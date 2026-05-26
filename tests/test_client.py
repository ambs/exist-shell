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
