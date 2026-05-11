"""Tests for the exec command."""

from unittest.mock import MagicMock

import pytest

from exist_shell.exceptions import ExistAuthError, ExistConnectionError, ExistQueryError
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
    monkeypatch.setattr("exist_shell.commands.exec.list_validators", lambda: [])
    result = runner.invoke(app, ["exec", "--list-validators"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# missing target
# ---------------------------------------------------------------------------

def test_missing_target_exits_1(runner):
    result = runner.invoke(app, ["exec"])
    assert result.exit_code == 1
    assert "TARGET" in result.output


# ---------------------------------------------------------------------------
# reading input
# ---------------------------------------------------------------------------

def test_exec_from_file(config_with_collection, client_mock, no_validation, tmp_path, runner):
    f = tmp_path / "query.xq"
    f.write_text('doc("test.xml")', encoding="utf-8")
    result = runner.invoke(app, ["exec", "myapp:/", "-f", str(f), "--no-fix"])
    assert result.exit_code == 0
    client_mock.execute_query.assert_called_once()


def test_exec_from_stdin(config_with_collection, client_mock, no_validation, runner):
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input='doc("test.xml")')
    assert result.exit_code == 0
    client_mock.execute_query.assert_called_once()


def test_exec_unreadable_file_exits_1(config_with_collection, client_mock, runner):
    result = runner.invoke(app, ["exec", "myapp:/", "-f", "/nonexistent/query.xq"])
    assert result.exit_code == 1
    assert "cannot read" in result.output


# ---------------------------------------------------------------------------
# preprocessing
# ---------------------------------------------------------------------------

def test_exec_preprocesses_by_default(config_with_collection, client_mock, no_validation, runner):
    result = runner.invoke(app, ["exec", "myapp:/"], input='doc("test.xml")')
    assert result.exit_code == 0
    sent_code = client_mock.execute_query.call_args[0][0]
    assert "xquery version" in sent_code


def test_exec_no_fix_skips_preprocessing(config_with_collection, client_mock, no_validation, runner):
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input='doc("test.xml")')
    assert result.exit_code == 0
    sent_code = client_mock.execute_query.call_args[0][0]
    assert "xquery version" not in sent_code


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------

def test_exec_no_validate_skips_validation(config_with_collection, client_mock, monkeypatch, runner):
    called = []
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: called.append(True) or ValidatorResult(ok=True, error=None),
    )
    runner.invoke(app, ["exec", "myapp:/", "--no-validate", "--no-fix"], input="1+1")
    assert not called


def test_exec_validation_failure_exits_1(config_with_collection, client_mock, monkeypatch, runner):
    monkeypatch.setattr(
        "exist_shell.commands.exec.validate_locally",
        lambda *a, **kw: ValidatorResult(ok=False, error="Unexpected token"),
    )
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="invalid !!!")
    assert result.exit_code == 1
    assert "Unexpected token" in result.output


def test_exec_unknown_validator_exits_1(config_with_collection, client_mock, monkeypatch, runner):
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
    client_mock.execute_query.side_effect = ExistQueryError("Unexpected token at line 1")
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="invalid !!!")
    assert result.exit_code == 1
    assert "XQuery error" in result.output


def test_exec_auth_error_exits_1(config_with_collection, client_mock, no_validation, runner):
    client_mock.execute_query.side_effect = ExistAuthError("url")
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 1
    assert "authentication failed" in result.output


def test_exec_connection_error_exits_1(config_with_collection, client_mock, no_validation, runner):
    client_mock.execute_query.side_effect = ExistConnectionError("url", Exception("refused"))
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 1


def test_exec_unknown_collection_exits_1(config_path, runner):
    result = runner.invoke(app, ["exec", "ghost:/"])
    assert result.exit_code == 1
    assert "not found" in result.output


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def test_exec_prints_query_output(config_with_collection, client_mock, no_validation, runner):
    client_mock.execute_query.return_value = "<answer>42</answer>"
    result = runner.invoke(app, ["exec", "myapp:/", "--no-fix"], input="1+1")
    assert result.exit_code == 0
    assert "<answer>42</answer>" in result.output
