"""Tests for the custom eXist-db REST API exceptions."""

import httpx

from exist_shell.exceptions import ExistConnectionError, ExistServerError


def test_connect_timeout_message_says_timed_out_connecting():
    """Connect timeout message says timed out connecting."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ConnectTimeout("timed out"))
    assert str(err) == "Timed out connecting to http://host/exist/rest/db: timed out"


def test_connect_error_message_says_cannot_connect():
    """Connect error message says cannot connect."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ConnectError("refused"))
    assert str(err) == "Cannot connect to http://host/exist/rest/db: refused"


def test_read_timeout_message_says_did_not_respond():
    """Read timeout message says did not respond."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ReadTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_write_timeout_message_says_did_not_respond():
    """Write timeout message says did not respond."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.WriteTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_pool_timeout_message_says_did_not_respond():
    """Pool timeout message says did not respond."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.PoolTimeout("timed out"))
    assert str(err) == "Server at http://host/exist/rest/db did not respond in time: timed out"


def test_read_error_message_falls_back_to_cannot_connect():
    """Read error message falls back to cannot connect."""
    err = ExistConnectionError("http://host/exist/rest/db", httpx.ReadError("broken pipe"))
    assert str(err) == "Cannot connect to http://host/exist/rest/db: broken pipe"


def test_server_error_message_includes_status_code_and_detail():
    """Server error message includes status code and detail."""
    err = ExistServerError(403, "Permission denied")
    assert str(err) == "Server returned HTTP 403: Permission denied"
    assert err.status_code == 403
    assert err.detail == "Permission denied"


def test_server_error_message_omits_colon_when_detail_empty():
    """Server error message omits colon when detail empty."""
    err = ExistServerError(409, "")
    assert str(err) == "Server returned HTTP 409"
