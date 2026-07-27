"""Tests for shared path validation and command utilities."""

import pytest
import typer
from typer.testing import CliRunner

from exist_shell.exceptions import ExistAuthError, ExistNotFoundError, ExistQueryError, ExistServerError
from exist_shell.utils import (
    check_xml_wellformed,
    handle_exist_errors,
    is_remote,
    parse_target,
    parse_user_at_server,
    validate_path,
    xq_escape,
)


# --- xq_escape ---

def test_xq_escape_passthrough_when_no_quotes():
    """Xq escape passthrough when no quotes."""
    assert xq_escape("hello") == "hello"


def test_xq_escape_doubles_double_quotes():
    """Xq escape doubles double quotes."""
    assert xq_escape('say "hello"') == 'say ""hello""'


def test_xq_escape_escapes_ampersand():
    """Xq escape escapes ampersand."""
    assert xq_escape("cats & dogs") == "cats &amp; dogs"


def test_xq_escape_escapes_ampersand_before_doubling_quotes():
    """Xq escape escapes ampersand before doubling quotes."""
    assert xq_escape('"A & B"') == '""A &amp; B""'


# --- check_xml_wellformed ---

def test_valid_xml_returns_none():
    """Valid xml returns none."""
    assert check_xml_wellformed(b"<root/>", "application/xml") is None


def test_valid_xml_with_declaration_returns_none():
    """Valid xml with declaration returns none."""
    assert check_xml_wellformed(b'<?xml version="1.0"?><root/>', "application/xml") is None


def test_malformed_xml_returns_error_string():
    """Malformed xml returns error string."""
    result = check_xml_wellformed(b"<root>", "application/xml")
    assert result is not None
    assert isinstance(result, str)


def test_malformed_xml_text_xml_mime():
    """Malformed xml text xml mime."""
    result = check_xml_wellformed(b"<unclosed", "text/xml")
    assert result is not None


def test_malformed_xml_plus_xml_mime():
    """Malformed xml plus xml mime."""
    result = check_xml_wellformed(b"<broken", "application/atom+xml")
    assert result is not None


def test_non_xml_mime_skips_check():
    """Non xml mime skips check."""
    assert check_xml_wellformed(b"not xml at all", "image/png") is None


def test_text_plain_skips_check():
    """Text plain skips check."""
    assert check_xml_wellformed(b"<root>", "text/plain") is None


def test_application_octet_stream_skips_check():
    """Application octet stream skips check."""
    assert check_xml_wellformed(b"\x00\x01\x02", "application/octet-stream") is None


# --- validate_path ---

def test_valid_simple_path():
    """Valid simple path."""
    validate_path("/subdir/doc.xml")


def test_valid_root_path():
    """Valid root path."""
    validate_path("/")


def test_valid_path_with_spaces():
    """Valid path with spaces."""
    validate_path("/sub dir/my doc.xml")


def test_rejects_dotdot_segment():
    """Rejects dotdot segment."""
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/../other/doc.xml")


def test_rejects_dotdot_in_middle():
    """Rejects dotdot in middle."""
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/subdir/../secret.xml")


def test_rejects_single_dot_segment():
    """Rejects single dot segment."""
    with pytest.raises(ValueError, match="traversal"):
        validate_path("/subdir/./doc.xml")


def test_rejects_null_byte():
    """Rejects null byte."""
    with pytest.raises(ValueError, match="null"):
        validate_path("/doc\x00.xml")


# --- parse_target ---

def test_parse_target_returns_nick_and_path():
    """Parse target returns nick and path."""
    assert parse_target("myapp:/docs/file.xml") == ("myapp", "/docs/file.xml")


def test_parse_target_adds_leading_slash():
    """Parse target adds leading slash."""
    assert parse_target("myapp:docs/file.xml") == ("myapp", "/docs/file.xml")


def test_parse_target_path_required_exits_on_missing(runner: CliRunner):
    """Parse target path required exits on missing."""
    from typer import Exit
    with pytest.raises((Exit, SystemExit)):
        parse_target("myapp")


def test_parse_target_path_not_required_defaults_to_root():
    """Parse target path not required defaults to root."""
    assert parse_target("myapp", path_required=False) == ("myapp", "/")


def test_parse_target_path_not_required_uses_given_path():
    """Parse target path not required uses given path."""
    assert parse_target("myapp:/sub", path_required=False) == ("myapp", "/sub")


def test_parse_target_rejects_traversal(runner: CliRunner):
    """Parse target rejects traversal."""
    from typer import Exit
    with pytest.raises((Exit, SystemExit)):
        parse_target("myapp:/../other")


# --- is_remote ---

def test_is_remote_no_colon_is_local(config_path):
    """Is remote no colon is local."""
    assert is_remote("/local/doc.xml") is False


def test_is_remote_configured_nick_is_remote(config_with_collection):
    """Is remote configured nick is remote."""
    assert is_remote("myapp:/docs/file.xml") is True


def test_is_remote_windows_drive_letter_backslash_is_local(config_path):
    """Is remote windows drive letter backslash is local."""
    assert is_remote(r"C:\data\doc.xml") is False


def test_is_remote_windows_drive_letter_forward_slash_is_local(config_path):
    """Is remote windows drive letter forward slash is local."""
    assert is_remote("C:/data/doc.xml") is False


def test_is_remote_posix_path_with_colon_in_component_is_local(config_path):
    """Is remote posix path with colon in component is local."""
    assert is_remote("some/dir:v2/file.xml") is False


def test_is_remote_unconfigured_bare_nick_stays_remote(config_path):
    """Typo'd or not-yet-configured nicks still resolve remote for a helpful error."""
    assert is_remote("ghost:/doc.xml") is True


# --- parse_user_at_server ---


def test_parse_user_at_server_no_at():
    """Parse user at server no at."""
    assert parse_user_at_server("alice") == ("alice", None)


def test_parse_user_at_server_with_server():
    """Parse user at server with server."""
    assert parse_user_at_server("alice@prod") == ("alice", "prod")


def test_parse_user_at_server_bare_at_server():
    """Parse user at server bare at server."""
    assert parse_user_at_server("@prod") == ("", "prod")


def test_parse_user_at_server_at_only():
    """Parse user at server at only."""
    assert parse_user_at_server("@") == ("", None)


def test_parse_user_at_server_multiple_at_uses_last():
    """Parse user at server multiple at uses last."""
    assert parse_user_at_server("a@b@prod") == ("a@b", "prod")


# --- handle_exist_errors ---


def test_handle_exist_errors_reports_not_found(capsys):
    """Handle exist errors reports not found."""
    with pytest.raises(typer.Exit):
        with handle_exist_errors("/doc.xml", "myapp", "prod"):
            raise ExistNotFoundError("/doc.xml")
    assert "not found in collection 'myapp'" in capsys.readouterr().err


def test_handle_exist_errors_reports_auth_failure(capsys):
    """Handle exist errors reports auth failure."""
    with pytest.raises(typer.Exit):
        with handle_exist_errors("/doc.xml", "myapp", "prod"):
            raise ExistAuthError("http://example.com")
    assert "authentication failed for server 'prod'" in capsys.readouterr().err


def test_handle_exist_errors_reports_server_error_instead_of_traceback(capsys):
    """A 403 (or any other non-401/404 status) must exit cleanly, not raise."""
    with pytest.raises(typer.Exit):
        with handle_exist_errors("/doc.xml", "myapp", "prod"):
            raise ExistServerError(403, "Permission denied")
    err = capsys.readouterr().err
    assert "403" in err
    assert "Permission denied" in err


def test_handle_exist_errors_reports_query_error(capsys):
    """Handle exist errors reports query error."""
    with pytest.raises(typer.Exit):
        with handle_exist_errors("/doc.xml", "myapp", "prod"):
            raise ExistQueryError("bad syntax")
    assert "XQuery error: bad syntax" in capsys.readouterr().err
