#!/usr/bin/env bash
# T06 — ls (after uploads)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T06_ls_after() {
    step "T06 — ls (after uploads)"

    # T06.1-4 — root listing contains all uploaded files and the auto-created subcollection
    assert_output "hello.xml" \
        "T06.1 ls testcol shows hello.xml" \
        "${EXSH[@]}" ls testcol

    assert_output "stdin.xml" \
        "T06.2 ls testcol shows stdin.xml" \
        "${EXSH[@]}" ls testcol

    assert_output "data.bin" \
        "T06.3 ls testcol shows data.bin" \
        "${EXSH[@]}" ls testcol

    assert_output "missing/" \
        "T06.4 ls testcol shows auto-created 'missing' subcollection" \
        "${EXSH[@]}" ls testcol

    # T06.5 — nested subcollection
    assert_output "sub/" \
        "T06.5 ls testcol:/missing shows 'sub'" \
        "${EXSH[@]}" ls testcol:/missing

    # T06.6 — document inside nested subcollection
    assert_output "doc.xml" \
        "T06.6 ls testcol:/missing/sub shows doc.xml" \
        "${EXSH[@]}" ls testcol:/missing/sub
}
