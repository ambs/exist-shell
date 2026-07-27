"""Tests for the exec command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistNotFoundError, ExistQueryError
from exist_shell.main import app
from exist_shell.xquery import ValidatorResult


@pytest.fixture
def client_mock(monkeypatch):
    """Mock ExistClient used by the exec command."""
    mock = MagicMock()
    monkeypatch.setattr("exist_shell.commands.exec.ExistClient", lambda _: mock)
    mock.__enter__.return_value.execute_query.return_value = "<result/>"
    return mock.__enter__.return_value


@pytest.fixture
def no_validation(monkeypatch):
    """Stub validate_locally to always pass so tests focus on other behaviour."""
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: ValidatorResult(ok=True, error=None),
    )


# ---------------------------------------------------------------------------
# --list-validators
# ---------------------------------------------------------------------------

def test_list_validators_exits_zero(monkeypatch, runner):
    """List validators exits zero."""
    monkeypatch.setattr(
        "exist_shell.commands.exec.list_validators",
        lambda: [("basex", "/usr/bin/basex"), ("saxon", None)],
    )
    result = runner.invoke(app, ["exec", "--list-validators"])
    assert result.exit_code == 0
    assert "basex" in result.output
    assert "/usr/bin/basex" in result.output
    assert "not installed" in result.output


def test_list_validators_does_not_require_target(monkeypatch, runner):
    """List validators does not require target."""
    monkeypatch.setattr("exist_shell.commands.exec.list_validators", lambda: [])
    result = runner.invoke(app, ["exec", "--list-validators"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# missing target
# ---------------------------------------------------------------------------

def test_missing_target_exits_1(runner):
    """Missing target exits 1."""
    result = runner.invoke(app, ["exec"])
    assert result.exit_code == 1
    assert "TARGET" in result.output


# ---------------------------------------------------------------------------
# reading input
# ---------------------------------------------------------------------------

def test_exec_from_file(config_with_collection, client_mock, no_validation, tmp_path, runner):
    """Exec from file."""
    f = tmp_path / "query.xq"
    f.write_text('doc("test.xml")', encoding="utf-8")
    result = runner.invoke(app, ["exec", "myapp:/", "-f", str(f), "--no-fix"])
    assert result.exit_code == 0
    client_mock.execute_query.assert_called_once()


def test_exec_from_stdin(config_with_collection, client_mock, no_validation, runner):
    """Exec from stdin."""
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input='doc("test.xml")')
    assert result.exit_code == 0
    client_mock.execute_query.assert_called_once()


def test_exec_unreadable_file_exits_1(config_with_collection, client_mock, runner):
    """Exec unreadable file exits 1."""
    result = runner.invoke(app, ["exec", "myapp:/", "-f", "/nonexistent/query.xq"])
    assert result.exit_code == 1
    assert "cannot read" in result.output


# ---------------------------------------------------------------------------
# preprocessing
# ---------------------------------------------------------------------------

def test_exec_preprocesses_by_default(config_with_collection, client_mock, no_validation, runner):
    """Exec preprocesses by default."""
    result = runner.invoke(app, ["exec", "myapp:/"], input='doc("test.xml")')
    assert result.exit_code == 0
    sent_code = client_mock.execute_query.call_args[0][0]
    assert "xquery version" in sent_code


def test_exec_no_fix_skips_preprocessing(config_with_collection, client_mock, no_validation, runner):
    """Exec no fix skips preprocessing."""
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input='doc("test.xml")')
    assert result.exit_code == 0
    sent_code = client_mock.execute_query.call_args[0][0]
    assert "xquery version" not in sent_code


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_exec_no_validate_skips_validation(config_with_collection, client_mock, monkeypatch, runner):
    """Exec no validate skips validation."""
    called = []
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: called.append(True) or ValidatorResult(ok=True, error=None),
    )
    runner.invoke(app, ["exec", "myapp:/", "--no-validate", "--no-fix"], input="1+1")
    assert not called


def test_exec_validation_failure_exits_1(config_with_collection, client_mock, monkeypatch, runner):
    """Exec validation failure exits 1."""
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: ValidatorResult(ok=False, error="Unexpected token"),
    )
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="invalid !!!")
    assert result.exit_code == 1
    assert "Unexpected token" in result.output


def test_exec_unknown_validator_exits_1(config_with_collection, client_mock, monkeypatch, runner):
    """Exec unknown validator exits 1."""
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: ValidatorResult(ok=False, error="unknown validator 'ghost'"),
    )
    result = runner.invoke(app, ["exec", "myapp:/", "--validator", "ghost", "--no-fix"], input="1+1")
    assert result.exit_code == 1
    assert "unknown validator" in result.output


# ---------------------------------------------------------------------------
# server errors
# ---------------------------------------------------------------------------

def test_exec_query_error_exits_1(config_with_collection, client_mock, no_validation, runner):
    """Exec query error exits 1."""
    client_mock.execute_query.side_effect = ExistQueryError("Unexpected token at line 1")
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="invalid !!!")
    assert result.exit_code == 1
    assert "XQuery error" in result.output


def test_exec_auth_error_exits_1(config_with_collection, client_mock, no_validation, runner):
    """Exec auth error exits 1."""
    client_mock.execute_query.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_exec_connection_error_exits_1(config_with_collection, client_mock, no_validation, runner):
    """Exec connection error exits 1."""
    client_mock.execute_query.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 1


def test_exec_unknown_collection_exits_1(config_path, runner):
    """Exec unknown collection exits 1."""
    result = runner.invoke(app, ["exec", "ghost:/"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def test_exec_prints_query_output(config_with_collection, client_mock, no_validation, runner):
    """Exec prints query output."""
    client_mock.execute_query.return_value = "<answer>42</answer>"
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 0
    assert "<answer>42</answer>" in result.output


# ---------------------------------------------------------------------------
# --resource
# ---------------------------------------------------------------------------

def test_exec_resource_executes_stored_resource(config_with_collection, client_mock, runner):
    """Exec resource executes stored resource."""
    client_mock.execute_resource.return_value = "<answer>42</answer>"
    result = runner.invoke(app, ["exec", "--resource", "myapp:/report.xql"])
    assert result.exit_code == 0
    assert "<answer>42</answer>" in result.output
    client_mock.execute_resource.assert_called_once_with("/db/myapp/report.xql", params=None)


def test_exec_resource_forwards_params(config_with_collection, client_mock, runner):
    """Exec resource forwards params."""
    client_mock.execute_resource.return_value = "ok"
    result = runner.invoke(
        app, ["exec", "--resource", "myapp:/report.xql", "-p", "from=2026-01-01", "-p", "to=2026-12-31"]
    )
    assert result.exit_code == 0
    client_mock.execute_resource.assert_called_once_with(
        "/db/myapp/report.xql", params={"from": "2026-01-01", "to": "2026-12-31"}
    )


def test_exec_resource_and_target_are_mutually_exclusive(config_with_collection, runner):
    """Exec resource and target are mutually exclusive."""
    result = runner.invoke(app, ["exec", "myapp:/", "--resource", "myapp:/report.xql"])
    assert result.exit_code == 1
    assert "mutually exclusive" in result.output


def test_exec_param_without_resource_exits_1(config_with_collection, client_mock, no_validation, runner):
    """Exec param without resource exits 1."""
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix", "-p", "a=b"], input="1+1")
    assert result.exit_code == 1
    assert "--param requires --resource" in result.output


def test_exec_resource_invalid_param_exits_1(config_with_collection, runner):
    """Exec resource invalid param exits 1."""
    result = runner.invoke(app, ["exec", "--resource", "myapp:/report.xql", "-p", "noequals"])
    assert result.exit_code == 1
    assert "invalid --param" in result.output


def test_exec_resource_requires_path(config_with_collection, runner):
    """Exec resource requires path."""
    result = runner.invoke(app, ["exec", "--resource", "myapp"])
    assert result.exit_code == 1
    assert "path is required" in result.output


def test_exec_resource_unknown_collection_exits_1(config_path, runner):
    """Exec resource unknown collection exits 1."""
    result = runner.invoke(app, ["exec", "--resource", "ghost:/report.xql"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_exec_resource_not_found_exits_1(config_with_collection, client_mock, runner):
    """Exec resource not found exits 1."""
    client_mock.execute_resource.side_effect = ExistNotFoundError("/db/myapp/ghost.xql")
    result = runner.invoke(app, ["exec", "--resource", "myapp:/ghost.xql"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_exec_resource_query_error_exits_1(config_with_collection, client_mock, runner):
    """Exec resource query error exits 1."""
    client_mock.execute_resource.side_effect = ExistQueryError("boom")
    result = runner.invoke(app, ["exec", "--resource", "myapp:/report.xql"])
    assert result.exit_code == 1
    assert "XQuery error" in result.output


def test_exec_resource_does_not_read_stdin(config_with_collection, client_mock, runner):
    """Exec resource does not read stdin."""
    client_mock.execute_resource.return_value = "ok"
    result = runner.invoke(app, ["exec", "--resource", "myapp:/report.xql"], input="should be ignored")
    assert result.exit_code == 0
    client_mock.execute_query.assert_not_called()
