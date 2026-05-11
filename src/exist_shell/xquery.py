"""XQuery preprocessing pipeline and local validator support."""

import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class ValidatorResult:
    """Result from a local XQuery validator run.

    Attributes:
        ok: True if the query is valid (or no validator was found).
        error: Human-readable error message, or None when ok is True.
    """

    ok: bool
    error: str | None


class XQueryValidator(Protocol):
    """Interface that every validator wrapper must implement."""

    name: str

    @classmethod
    def probe(cls) -> "XQueryValidator | None":
        """Find the validator binary and return a ready instance, or None if not installed.

        Returns:
            An initialised validator bound to the discovered binary, or None.
        """
        ...

    def validate(self, code: str) -> ValidatorResult:
        """Validate XQuery source code.

        Args:
            code: XQuery source code to validate.

        Returns:
            ValidatorResult with ok=True on success, or ok=False with an error message.
        """
        ...


class BasexValidator:
    """Validator wrapper for BaseX (https://basex.org).

    BaseX accepts ``INSPECT XQUERY <file>`` via its command-line client.
    A parse error causes a non-zero exit code and the error text on stderr.
    """

    name = "basex"

    def __init__(self, binary: str) -> None:
        """Initialise with a known-good path to the basex binary."""
        self._binary = binary

    @classmethod
    def probe(cls) -> "BasexValidator | None":
        """Find the basex binary on PATH and return a bound instance, or None.

        Returns:
            BasexValidator bound to the discovered binary, or None if not found.
        """
        binary = shutil.which("basex")
        return cls(binary) if binary else None

    def validate(self, code: str) -> ValidatorResult:
        """Validate XQuery by running it through basex in parse-only mode.

        Args:
            code: XQuery source code to validate.

        Returns:
            ValidatorResult indicating success or the first reported error.
        """
        with tempfile.NamedTemporaryFile(suffix=".xq", delete=False, mode="w", encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        try:
            result = subprocess.run(
                [self._binary, "-c", f"INSPECT XQUERY {tmp}"],
                capture_output=True,
                text=True,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)
        if result.returncode == 0:
            return ValidatorResult(ok=True, error=None)
        detail = (result.stderr or result.stdout).strip()
        return ValidatorResult(ok=False, error=detail or "validation failed")


class SaxonValidator:
    """Validator wrapper for Saxon (https://www.saxonica.com).

    Looks for a ``saxon`` wrapper script on PATH (the standard install name on
    most package managers).  Saxon is invoked with ``-q:<file>``; a non-zero
    exit code signals a parse or static error.
    """

    name = "saxon"

    def __init__(self, binary: str) -> None:
        """Initialise with a known-good path to the saxon binary."""
        self._binary = binary

    @classmethod
    def probe(cls) -> "SaxonValidator | None":
        """Find the saxon binary on PATH and return a bound instance, or None.

        Returns:
            SaxonValidator bound to the discovered binary, or None if not found.
        """
        binary = shutil.which("saxon")
        return cls(binary) if binary else None

    def validate(self, code: str) -> ValidatorResult:
        """Validate XQuery by running it through Saxon.

        Args:
            code: XQuery source code to validate.

        Returns:
            ValidatorResult indicating success or the first reported error.
        """
        with tempfile.NamedTemporaryFile(suffix=".xq", delete=False, mode="w", encoding="utf-8") as f:
            f.write(code)
            tmp = f.name
        try:
            result = subprocess.run(
                [self._binary, f"-q:{tmp}"],
                capture_output=True,
                text=True,
            )
        finally:
            Path(tmp).unlink(missing_ok=True)
        if result.returncode == 0:
            return ValidatorResult(ok=True, error=None)
        detail = (result.stderr or result.stdout).strip()
        return ValidatorResult(ok=False, error=detail or "validation failed")


# Registry of known validator classes in preference order.
_VALIDATORS: list[type[BasexValidator] | type[SaxonValidator]] = [
    BasexValidator,
    SaxonValidator,
]

_VALIDATORS_BY_NAME: dict[str, type[BasexValidator] | type[SaxonValidator]] = {
    cls.name: cls for cls in _VALIDATORS
}


def list_validators() -> list[tuple[str, str | None]]:
    """Return each known validator paired with its installed path, or None.

    Returns:
        List of ``(name, path)`` tuples; path is None when not installed.
    """
    return [(cls.name, shutil.which(cls.name)) for cls in _VALIDATORS]


def validate_locally(code: str, *, validator: str | None = None) -> ValidatorResult:
    """Validate XQuery using the first locally available validator.

    When ``validator`` is given, that specific validator is required; the call
    fails if it is unknown or not installed.  When omitted, the first installed
    validator in the registry is used.  If none are installed, returns ok=True
    so the caller can proceed without blocking.

    Args:
        code: XQuery source code to validate.
        validator: Name of the validator to use, or None for auto-discovery.

    Returns:
        ValidatorResult from the chosen or first available validator.
    """
    if validator is not None:
        cls = _VALIDATORS_BY_NAME.get(validator)
        if cls is None:
            known = ", ".join(_VALIDATORS_BY_NAME)
            return ValidatorResult(ok=False, error=f"unknown validator '{validator}'; known: {known}")
        v = cls.probe()
        if v is None:
            return ValidatorResult(ok=False, error=f"validator '{validator}' is not installed")
        return v.validate(code)
    for cls in _VALIDATORS:
        v = cls.probe()
        if v is not None:
            return v.validate(code)
    return ValidatorResult(ok=True, error=None)


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------


def _ensure_version(code: str) -> str:
    """Prepend ``xquery version "3.1";`` if no version declaration is present.

    Args:
        code: XQuery source code.

    Returns:
        Code with a version declaration at the top.
    """
    if "xquery version" in code.lower():
        return code
    return 'xquery version "3.1";\n' + code


def _ensure_functx(code: str) -> str:
    """Add the functx module import when ``functx:`` is used but not declared.

    Args:
        code: XQuery source code.

    Returns:
        Code with the functx import inserted after the version declaration,
        or unchanged if functx is already imported or not referenced.
    """
    if "functx:" not in code:
        return code
    if "namespace functx" in code:
        return code
    import_line = (
        'import module namespace functx = "http://www.functx.com"'
        ' at "functx/functx.xq";\n'
    )
    lines = code.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.lower().startswith("xquery version"):
            lines.insert(i + 1, import_line)
            return "".join(lines)
    return import_line + code


# Ordered list of transformations applied by preprocess().
_PIPELINE: list[Callable[[str], str]] = [
    _ensure_version,
    _ensure_functx,
]


def preprocess(code: str) -> str:
    """Apply all preprocessing transformations to XQuery source code.

    Transformations are applied in pipeline order.  Each step is a pure
    ``str -> str`` function.

    Args:
        code: Raw XQuery source code.

    Returns:
        Preprocessed XQuery source code.
    """
    for step in _PIPELINE:
        code = step(code)
    return code
