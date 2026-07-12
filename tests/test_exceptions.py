import httpx

from exist_shell.exceptions import ExistConnectionError


def test_connect_timeout_message_says_timed_out_connecting():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ConnectTimeout("timed out"))
    assert str(err) == "Timed out connecting to http://host/exist/rest/db: timed out"


def test_connect_error_message_says_cannot_connect():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ConnectError("refused"))
    assert str(err) == "Cannot connect to http://host/exist/rest/db: refused"


def test_read_timeout_message_says_did_not_respond():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ReadTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_write_timeout_message_says_did_not_respond():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.WriteTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_pool_timeout_message_says_did_not_respond():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.PoolTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_read_error_message_falls_back_to_cannot_connect():
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ReadError("broken pipe"))
    assert str(err) == "Cannot connect to http://host/exist/rest/db: broken pipe"
