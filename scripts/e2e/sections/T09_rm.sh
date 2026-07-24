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

    # T09.7 — multi-target: first target missing → exits before second is attempted
    assert_output "not found in collection" \
        "T09.7 rm with missing first target fails immediately" \
        "${EXSH[@]}" rm testcol:/gone.xml testcol:/hello.xml
    assert_output "hello.xml" \
        "T09.7 hello.xml preserved (second target never reached)" \
        "${EXSH[@]}" ls testcol

    # T09.8 — rm on a collection path is refused without --recursive
    printf '<x/>' > "${TMPDIR_E2E}/rmtest_child.xml"
    assert_exit0 "T09.8 setup: mkdir rmtest" \
        "${EXSH[@]}" mkdir testcol:/rmtest
    assert_exit0 "T09.8 setup: put rmtest/child.xml" \
        "${EXSH[@]}" put testcol:/rmtest/child.xml -f "${TMPDIR_E2E}/rmtest_child.xml"

    assert_output "is a collection" \
        "T09.8 rm on collection without --recursive is refused" \
        "${EXSH[@]}" rm testcol:/rmtest
    assert_output "rmtest/" \
        "T09.8 collection survives the refused rm" \
        "${EXSH[@]}" ls testcol

    # T09.9 — rm --recursive --yes deletes the collection and everything under it
    # (declined-confirmation behavior is covered by the unit tests; e2e follows
    # the same --yes-only convention already used by user/group rm above)
    assert_exit0 "T09.9 rm --recursive --yes deletes collection" \
        "${EXSH[@]}" rm --recursive --yes testcol:/rmtest
    assert_output_absent "rmtest" \
        "T09.9 collection no longer listed" \
        "${EXSH[@]}" ls testcol
}
