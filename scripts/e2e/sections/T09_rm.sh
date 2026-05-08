#!/usr/bin/env bash
# T09 — rm (single, multi, not-found, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T09_rm() {
    step "T09 — rm"

    # T09.1 — delete single file
    assert_exit0 "T09.1 rm single file" \
        "${EXSH[@]}" rm testcol:/hello_copy.xml

    # T09.2 — verify file is gone from listing
    assert_output_absent "hello_copy.xml" \
        "T09.2 ls no longer shows hello_copy.xml" \
        "${EXSH[@]}" ls testcol

    # T09.3 — delete multiple files in one call
    assert_exit0 "T09.3 rm multiple files" \
        "${EXSH[@]}" rm testcol:/stdin.xml testcol:/hello_r2r.xml

    # T09.4 — delete already-deleted file
    assert_output "not found in collection" \
        "T09.4 rm already-deleted file fails" \
        "${EXSH[@]}" rm testcol:/hello_copy.xml

    # T09.5 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T09.5 rm unknown nick fails" \
        "${EXSH[@]}" rm ghost:/x.xml

    # T09.6 — missing path (no colon)
    assert_output "path is required" \
        "T09.6 rm without path fails" \
        "${EXSH[@]}" rm testcol
}
