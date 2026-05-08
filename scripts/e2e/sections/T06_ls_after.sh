#!/usr/bin/env bash
# T06 — ls (after uploads)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T06_ls_after() {
    step "T06 — ls (after uploads)"

    # T06.1-4 — root listing contains all uploaded files and the auto-created subcollection
    _run "${EXSH[@]}" ls testcol
    assert_in_last "hello.xml" "T06.1 ls testcol shows hello.xml"
    assert_in_last "stdin.xml" "T06.2 ls testcol shows stdin.xml"
    assert_in_last "data.bin"  "T06.3 ls testcol shows data.bin"
    assert_in_last "missing/"  "T06.4 ls testcol shows auto-created 'missing' subcollection"

    # T06.5 — nested subcollection
    assert_output "sub/" \
        "T06.5 ls testcol:/missing shows 'sub'" \
        "${EXSH[@]}" ls testcol:/missing

    # T06.6 — document inside nested subcollection
    assert_output "doc.xml" \
        "T06.6 ls testcol:/missing/sub shows doc.xml" \
        "${EXSH[@]}" ls testcol:/missing/sub
}
