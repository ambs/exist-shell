#!/usr/bin/env bash
# T07 — cat (text, binary, --raw, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T07_cat() {
    step "T07 — cat"

    # T07.1 — cat XML document
    assert_output "<hello>world</hello>" \
        "T07.1 cat XML file prints content" \
        "${EXSH[@]}" cat testcol:/hello.xml

    # T07.2 — cat stdin-uploaded document
    assert_output "<from>stdin</from>" \
        "T07.2 cat stdin-uploaded file prints content" \
        "${EXSH[@]}" cat testcol:/stdin.xml

    # T07.3 — binary file rejected without --raw
    assert_output "is binary" \
        "T07.3 cat binary without --raw fails" \
        "${EXSH[@]}" cat testcol:/data.bin

    # T07.4 — binary file written correctly with --raw
    local code=0
    "${EXSH[@]}" cat testcol:/data.bin --raw > "${TMPDIR_E2E}/data_dl.bin" 2>/dev/null || code=$?
    if [[ $code -ne 0 ]]; then
        _LAST_OUTPUT="exit code: ${code}"
        fail "T07.4 cat binary --raw (expected exit 0, got ${code})"
    elif cmp -s "${TMPDIR_E2E}/data.bin" "${TMPDIR_E2E}/data_dl.bin"; then
        ok "T07.4 cat binary --raw writes correct bytes"
    else
        _LAST_OUTPUT="downloaded file differs from original"
        fail "T07.4 cat binary --raw writes correct bytes"
    fi

    # T07.5 — non-existent document
    assert_output "not found in collection" \
        "T07.5 cat non-existent path fails" \
        "${EXSH[@]}" cat testcol:/nonexistent.xml

    # T07.6 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T07.6 cat unknown nick fails" \
        "${EXSH[@]}" cat ghost:/hello.xml

    # T07.7 — missing path (no colon)
    assert_output "path is required" \
        "T07.7 cat without path fails" \
        "${EXSH[@]}" cat testcol
}
