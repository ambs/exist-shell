"""Tests for the xquery preprocessing pipeline and local validator support."""

import subprocess
from unittest.mock import MagicMock

import pytest

from exist_shell.xquery import (
    BasexValidator,
    SaxonValidator,
    ValidatorResult,
    _ensure_functx,
    _ensure_version,
    list_validators,
    preprocess,
    validate_locally,
)


# ---------------------------------------------------------------------------
# _ensure_version
# ---------------------------------------------------------------------------

def test_ensure_version_adds_declaration_when_missing():
    """Ensure version adds declaration when missing."""
    result = _ensure_version('doc("test.xml")')
    assert result.startswith('xquery version "3.1";\n')


def test_ensure_version_leaves_existing_declaration():
    """Ensure version leaves existing declaration."""
    code = 'xquery version "1.0";\ndoc("test.xml")'
    assert _ensure_version(code) == code


def test_ensure_version_is_case_insensitive():
    """Ensure version is case insensitive."""
    code = 'XQuery Version "3.1";\ndoc("test.xml")'
    assert _ensure_version(code) == code


# ---------------------------------------------------------------------------
# _ensure_functx
# ---------------------------------------------------------------------------

def test_ensure_functx_adds_import_when_functx_used():
    """Ensure functx adds import when functx used."""
    code = 'xquery version "3.1";\nfunctx:capitalize-first("hello")'
    result = _ensure_functx(code)
    assert 'import module namespace functx' in result


def test_ensure_functx_inserts_after_version_line():
    """Ensure functx inserts after version line."""
    code = 'xquery version "3.1";\nfunctx:capitalize-first("hello")'
    lines = _ensure_functx(code).splitlines()
    assert lines[0].startswith('xquery version')
    assert lines[1].startswith('import module namespace functx')


def test_ensure_functx_leaves_code_when_no_functx_ref():
    """Ensure functx leaves code when no functx ref."""
    code = 'xquery version "3.1";\ndoc("test.xml")'
    assert _ensure_functx(code) == code


def test_ensure_functx_leaves_code_when_already_declared():
    """Ensure functx leaves code when already declared."""
    code = (
        'xquery version "3.1";\n'
        'import module namespace functx = "http://www.functx.com" at "functx/functx.xq";\n'
        'functx:capitalize-first("hello")'
    )
    assert _ensure_functx(code) == code


def test_ensure_functx_prepends_when_no_version_line():
    """Ensure functx prepends when no version line."""
    code = 'functx:capitalize-first("hello")'
    result = _ensure_functx(code)
    assert result.startswith('import module namespace functx')


# ---------------------------------------------------------------------------
# preprocess
# ---------------------------------------------------------------------------

def test_preprocess_adds_version_and_functx():
    """Preprocess adds version and functx."""
    code = 'functx:capitalize-first("hello")'
    result = preprocess(code)
    assert 'xquery version "3.1"' in result
    assert 'import module namespace functx' in result


def test_preprocess_does_not_duplicate_version():
    """Preprocess does not duplicate version."""
    code = 'xquery version "3.1";\ndoc("test.xml")'
    result = preprocess(code)
    assert result.count('xquery version') == 1


# ---------------------------------------------------------------------------
# BasexValidator
# ---------------------------------------------------------------------------

def test_basex_probe_returns_none_when_not_found(monkeypatch):
    """Basex probe returns none when not found."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: None)
    assert BasexValidator.probe() is None


def test_basex_probe_returns_instance_when_found(monkeypatch):
    """Basex probe returns instance when found."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: "/usr/bin/basex")
    v = BasexValidator.probe()
    assert isinstance(v, BasexValidator)
    assert v._binary == "/usr/bin/basex"


def test_basex_validate_returns_ok_on_success(monkeypatch, tmp_path):
    """Basex validate returns ok on success."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    monkeypatch.setattr("exist_shell.xquery.subprocess.run", lambda *a, **kw: completed)
    v = BasexValidator("/usr/bin/basex")
    assert v.validate('doc("test.xml")') == ValidatorResult(ok=True, error=None)


def test_basex_validate_returns_error_on_failure(monkeypatch):
    """Basex validate returns error on failure."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 1
    completed.stderr = "Unexpected token"
    completed.stdout = ""
    monkeypatch.setattr("exist_shell.xquery.subprocess.run", lambda *a, **kw: completed)
    v = BasexValidator("/usr/bin/basex")
    result = v.validate("invalid xquery !!!")
    assert result.ok is False
    assert result.error is not None
    assert "Unexpected token" in result.error


def test_basex_validate_falls_back_to_stdout_when_stderr_empty(monkeypatch):
    """Basex validate falls back to stdout when stderr empty."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 1
    completed.stderr = ""
    completed.stdout = "Parse error on line 1"
    monkeypatch.setattr("exist_shell.xquery.subprocess.run", lambda *a, **kw: completed)
    v = BasexValidator("/usr/bin/basex")
    result = v.validate("invalid xquery !!!")
    assert result.error is not None
    assert "Parse error" in result.error


# ---------------------------------------------------------------------------
# SaxonValidator
# ---------------------------------------------------------------------------

def test_saxon_probe_returns_none_when_not_found(monkeypatch):
    """Saxon probe returns none when not found."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: None)
    assert SaxonValidator.probe() is None


def test_saxon_probe_returns_instance_when_found(monkeypatch):
    """Saxon probe returns instance when found."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: "/usr/bin/saxon")
    v = SaxonValidator.probe()
    assert isinstance(v, SaxonValidator)
    assert v._binary == "/usr/bin/saxon"


def test_saxon_validate_returns_ok_on_success(monkeypatch):
    """Saxon validate returns ok on success."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 0
    monkeypatch.setattr("exist_shell.xquery.subprocess.run", lambda *a, **kw: completed)
    v = SaxonValidator("/usr/bin/saxon")
    assert v.validate('doc("test.xml")') == ValidatorResult(ok=True, error=None)


def test_saxon_validate_returns_error_on_failure(monkeypatch):
    """Saxon validate returns error on failure."""
    completed = MagicMock(spec=subprocess.CompletedProcess)
    completed.returncode = 1
    completed.stderr = "Static error"
    completed.stdout = ""
    monkeypatch.setattr("exist_shell.xquery.subprocess.run", lambda *a, **kw: completed)
    v = SaxonValidator("/usr/bin/saxon")
    result = v.validate("invalid xquery !!!")
    assert result.ok is False
    assert result.error is not None
    assert "Static error" in result.error


# ---------------------------------------------------------------------------
# validate_locally
# ---------------------------------------------------------------------------

def test_validate_locally_uses_first_installed(monkeypatch):
    """Validate locally uses first installed."""
    mock_validator = MagicMock()
    mock_validator.probe.return_value = mock_validator
    mock_validator.validate.return_value = ValidatorResult(ok=True, error=None)
    monkeypatch.setattr("exist_shell.xquery._VALIDATORS", [mock_validator])
    result = validate_locally("xquery version '3.1'; 1+1")
    mock_validator.validate.assert_called_once()
    assert result.ok is True


def test_validate_locally_skips_silently_when_none_installed(monkeypatch):
    """Validate locally skips silently when none installed."""
    mock_validator = MagicMock()
    mock_validator.probe.return_value = None
    monkeypatch.setattr("exist_shell.xquery._VALIDATORS", [mock_validator])
    result = validate_locally("xquery version '3.1'; 1+1")
    assert result.ok is True
    assert result.error is None


def test_validate_locally_uses_named_validator(monkeypatch):
    """Validate locally uses named validator."""
    mock_validator = MagicMock()
    mock_validator.name = "myval"
    mock_validator.probe.return_value = mock_validator
    mock_validator.validate.return_value = ValidatorResult(ok=True, error=None)
    monkeypatch.setattr("exist_shell.xquery._VALIDATORS_BY_NAME", {"myval": mock_validator})
    result = validate_locally("1+1", validator="myval")
    mock_validator.validate.assert_called_once()
    assert result.ok is True


def test_validate_locally_named_validator_unknown_returns_error(monkeypatch):
    """Validate locally named validator unknown returns error."""
    monkeypatch.setattr("exist_shell.xquery._VALIDATORS_BY_NAME", {})
    result = validate_locally("1+1", validator="nonexistent")
    assert result.ok is False
    assert result.error is not None
    assert "unknown validator" in result.error


def test_validate_locally_named_validator_not_installed_returns_error(monkeypatch):
    """Validate locally named validator not installed returns error."""
    mock_cls = MagicMock()
    mock_cls.probe.return_value = None
    monkeypatch.setattr("exist_shell.xquery._VALIDATORS_BY_NAME", {"myval": mock_cls})
    result = validate_locally("1+1", validator="myval")
    assert result.ok is False
    assert result.error is not None
    assert "not installed" in result.error


# ---------------------------------------------------------------------------
# list_validators
# ---------------------------------------------------------------------------

def test_list_validators_returns_all_known(monkeypatch):
    """List validators returns all known."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: None)
    result = list_validators()
    names = [name for name, _ in result]
    assert "basex" in names
    assert "saxon" in names


def test_list_validators_shows_installed_path(monkeypatch):
    """List validators shows installed path."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda name: f"/usr/bin/{name}")
    result = list_validators()
    for name, path in result:
        assert path == f"/usr/bin/{name}"


def test_list_validators_shows_none_for_missing(monkeypatch):
    """List validators shows none for missing."""
    monkeypatch.setattr("exist_shell.xquery.shutil.which", lambda _: None)
    result = list_validators()
    for _, path in result:
        assert path is None
