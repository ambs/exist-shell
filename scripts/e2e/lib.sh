#!/usr/bin/env bash
# Shared helpers for e2e tests.
# Sourced by scripts/e2e.sh — do not execute directly.

PASS=0
FAIL=0
_LAST_OUTPUT=""

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

step() {
    echo ""
    echo "=== $* ==="
}

ok() {
    PASS=$(( PASS + 1 ))
    printf "  ✓ %s\n" "$*"
}

fail() {
    FAIL=$(( FAIL + 1 ))
    printf "  ✗ %s\n" "$*"
    debug_info
    exit 1
}

debug_info() {
    echo ""
    echo "--- last command output ---"
    printf "%s\n" "${_LAST_OUTPUT}"
    echo "--- docker logs (tail 20) ---"
    docker logs "${CONTAINER:-exsh-e2e}" 2>&1 | tail -20 || true
    echo "--- exsh config ---"
    cat "${EXSH_CONFIG:-}" 2>/dev/null || echo "(no config)"
}

# ---------------------------------------------------------------------------
# Run helper — captures combined stdout+stderr, returns the command's exit code.
# ---------------------------------------------------------------------------

_run() {
    local _exit=0
    _LAST_OUTPUT="$("$@" 2>&1)" || _exit=$?
    return $_exit
}

# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

assert_exit0() {
    local desc="$1"; shift
    local code=0
    _run "$@" || code=$?
    if [[ $code -eq 0 ]]; then
        ok "$desc"
    else
        fail "$desc (expected exit 0, got ${code})"
    fi
}

assert_exit1() {
    local desc="$1"; shift
    local code=0
    _run "$@" || code=$?
    if [[ $code -ne 0 ]]; then
        ok "$desc"
    else
        fail "$desc (expected non-zero exit, got 0)"
    fi
}

assert_empty_output() {
    local desc="$1"; shift
    local code=0
    _run "$@" || code=$?
    if [[ -z "${_LAST_OUTPUT}" ]]; then
        ok "$desc"
    else
        fail "$desc (expected empty output, got: ${_LAST_OUTPUT}; exit=${code})"
    fi
}

# assert_output <needle> <desc> <cmd...>
assert_output() {
    local needle="$1"; shift
    local desc="$1"; shift
    local code=0
    _run "$@" || code=$?
    if echo "${_LAST_OUTPUT}" | grep -qF -- "$needle"; then
        ok "$desc"
    else
        fail "$desc (expected '${needle}' in output; exit=${code})"
    fi
}

# assert_output_absent <needle> <desc> <cmd...>
assert_output_absent() {
    local needle="$1"; shift
    local desc="$1"; shift
    local code=0
    _run "$@" || code=$?
    if echo "${_LAST_OUTPUT}" | grep -qF -- "$needle"; then
        fail "$desc (unexpected '${needle}' found in output; exit=${code})"
    else
        ok "$desc"
    fi
}

# assert_file_eq <file> <expected_content> <desc>
assert_file_eq() {
    local file="$1"
    local expected="$2"
    local desc="$3"
    local actual
    actual="$(cat "$file")"
    if [[ "$actual" == "$expected" ]]; then
        ok "$desc"
    else
        _LAST_OUTPUT="$(printf "expected: %s\n  actual: %s" "$expected" "$actual")"
        fail "$desc"
    fi
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
    echo ""
    echo "───────────────────────────────"
    printf "  %d passed, %d failed\n" "$PASS" "$FAIL"
    if [[ $FAIL -eq 0 ]]; then
        echo "  All checks passed."
    else
        echo "  FAILURES DETECTED."
    fi
    echo "───────────────────────────────"
}
