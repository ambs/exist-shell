#!/usr/bin/env bash
# T14 — exec (XQuery execution)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T14_exec() {
    step "T14 — exec"

    # T14.1 — basic arithmetic from stdin
    # _run does not support shell pipes, so capture manually.
    local code=0
    _LAST_OUTPUT=$(echo '1+1' | "${EXSH[@]}" exec testcol:/ --no-validate 2>&1) || code=$?
    if [[ $code -ne 0 ]]; then
        fail "T14.1 exec arithmetic from stdin (expected exit 0, got ${code})"
    elif echo "${_LAST_OUTPUT}" | grep -qF "2"; then
        ok "T14.1 exec arithmetic from stdin prints result"
    else
        fail "T14.1 exec arithmetic from stdin (expected '2' in output; got: ${_LAST_OUTPUT})"
    fi

    # T14.2 — count documents in collection from file
    printf 'count(collection("/db/testcol"))' > "${TMPDIR_E2E}/count.xq"
    code=0
    _LAST_OUTPUT=$("${EXSH[@]}" exec testcol:/ -f "${TMPDIR_E2E}/count.xq" --no-validate 2>&1) || code=$?
    if [[ $code -ne 0 ]]; then
        fail "T14.2 exec count query from file (expected exit 0, got ${code})"
    elif echo "${_LAST_OUTPUT}" | grep -qE '[0-9]+'; then
        ok "T14.2 exec count query from file prints integer result"
    else
        fail "T14.2 exec count query from file (expected integer in output; got: ${_LAST_OUTPUT})"
    fi

    # T14.3 — retrieve document content from file
    # hello.xml was modified to contain "eXist" by T11.2.
    printf 'doc("/db/testcol/hello.xml")' > "${TMPDIR_E2E}/doc.xq"
    assert_output "eXist" \
        "T14.3 exec doc() query from file prints document content" \
        "${EXSH[@]}" exec testcol:/ -f "${TMPDIR_E2E}/doc.xq" --no-validate

    # T14.4 — preprocessing adds version declaration to a bare expression
    # The query has no xquery version line; preprocessing prepends one before sending.
    code=0
    _LAST_OUTPUT=$(echo 'count(/*)' | "${EXSH[@]}" exec testcol:/ --no-validate 2>&1) || code=$?
    if [[ $code -eq 0 ]]; then
        ok "T14.4 exec bare expression accepted after preprocessing adds version declaration"
    else
        fail "T14.4 exec bare expression with preprocessing (expected exit 0, got ${code})"
    fi

    # T14.5 — --no-fix passes a complete query through unchanged
    code=0
    _LAST_OUTPUT=$(echo 'xquery version "3.1"; count(/*)' | "${EXSH[@]}" exec testcol:/ --no-fix --no-validate 2>&1) || code=$?
    if [[ $code -eq 0 ]]; then
        ok "T14.5 exec complete query with --no-fix accepted unchanged"
    else
        fail "T14.5 exec complete query with --no-fix (expected exit 0, got ${code})"
    fi

    # T14.6 — preprocessing adds functx import when functx: is referenced
    # Guard: if the server returns a namespace error, functx is not installed on
    # this image — print an informational note and skip rather than fail.
    printf 'functx:capitalize-first("hello")' > "${TMPDIR_E2E}/functx.xq"
    code=0
    _LAST_OUTPUT=$("${EXSH[@]}" exec testcol:/ -f "${TMPDIR_E2E}/functx.xq" --no-validate 2>&1) || code=$?
    if [[ $code -eq 0 ]] && echo "${_LAST_OUTPUT}" | grep -qF "Hello"; then
        ok "T14.6 exec functx query: preprocessing added version declaration and functx import"
    elif [[ $code -ne 0 ]] && echo "${_LAST_OUTPUT}" | grep -qiE "namespace|module"; then
        printf "  - T14.6 exec functx preprocessing (skipped — functx not installed on this image)\n"
        printf "  - T14.7 exec functx without preprocessing (skipped — functx not installed on this image)\n"
    else
        fail "T14.6 exec functx query with preprocessing (code=${code}; output: ${_LAST_OUTPUT})"
    fi

    # T14.7 — --no-fix leaves functx.xq untouched; server rejects missing namespace
    # Only runs when functx.xq was already confirmed usable in T14.6 (guard above
    # handles the skip case together with T14.6).
    if [[ $code -eq 0 ]]; then
        code=0
        _LAST_OUTPUT=$("${EXSH[@]}" exec testcol:/ -f "${TMPDIR_E2E}/functx.xq" --no-fix --no-validate 2>&1) || code=$?
        if [[ $code -ne 0 ]] && echo "${_LAST_OUTPUT}" | grep -qF "XQuery error"; then
            ok "T14.7 exec functx without preprocessing rejected by server with XQuery error"
        elif [[ $code -eq 0 ]]; then
            fail "T14.7 exec functx without preprocessing (expected exit 1, got 0)"
        else
            fail "T14.7 exec functx without preprocessing (expected 'XQuery error' in output; got: ${_LAST_OUTPUT})"
        fi
    fi

    # T14.8 — malformed XQuery rejected by server
    code=0
    _LAST_OUTPUT=$(echo 'this is not valid !!!' | "${EXSH[@]}" exec testcol:/ --no-fix --no-validate 2>&1) || code=$?
    if [[ $code -ne 0 ]] && echo "${_LAST_OUTPUT}" | grep -qF "XQuery error"; then
        ok "T14.8 exec malformed query rejected by server with XQuery error"
    elif [[ $code -eq 0 ]]; then
        fail "T14.8 exec malformed query (expected exit 1, got 0)"
    else
        fail "T14.8 exec malformed query (expected 'XQuery error' in output; got: ${_LAST_OUTPUT})"
    fi

    # T14.9 — --list-validators exits 0 and lists known validator names
    assert_output "basex" \
        "T14.9 --list-validators lists basex" \
        "${EXSH[@]}" exec --list-validators
    assert_in_last "saxon" \
        "T14.9 --list-validators lists saxon"

    # T14.10 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T14.10 exec unknown collection fails" \
        "${EXSH[@]}" exec ghost:/ --no-validate

    # T14.11 — missing target
    assert_output "TARGET" \
        "T14.11 exec without target fails" \
        "${EXSH[@]}" exec

    # T14.12 — unreadable file
    assert_output "cannot read" \
        "T14.12 exec unreadable file fails" \
        "${EXSH[@]}" exec testcol:/ -f "/nonexistent/query.xq"

    # T14.13 — output is pipe-friendly well-formed XML
    # doc() returns the document; xmllint --format - parses and pretty-prints it.
    # A non-zero exit from xmllint means the output was not valid XML.
    code=0
    _LAST_OUTPUT=$(
        echo 'doc("/db/testcol/hello.xml")' \
        | "${EXSH[@]}" exec testcol:/ --no-validate \
        | xmllint --format - 2>&1
    ) || code=$?
    if [[ $code -eq 0 ]]; then
        ok "T14.13 exec output pipes into xmllint as well-formed XML"
    else
        fail "T14.13 exec output pipes into xmllint (xmllint exited ${code}; output: ${_LAST_OUTPUT})"
    fi
}
