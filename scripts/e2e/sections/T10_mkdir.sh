#!/usr/bin/env bash
# T10 — mkdir (create, idempotent, nested, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T10_mkdir() {
    step "T10 — mkdir"

    # T10.1 — create a new collection
    assert_exit0 "T10.1 mkdir creates new collection" \
        "${EXSH[@]}" mkdir testcol:/newdir

    # T10.2 — verify it appears in listing
    assert_output "newdir/" \
        "T10.2 ls shows newdir/" \
        "${EXSH[@]}" ls testcol

    # T10.3 — idempotent: creating again succeeds
    assert_exit0 "T10.3 mkdir existing collection is idempotent" \
        "${EXSH[@]}" mkdir testcol:/newdir

    # T10.4 — nested path: eXist auto-creates intermediate collection
    assert_exit0 "T10.4 mkdir nested path auto-creates parent" \
        "${EXSH[@]}" mkdir testcol:/nested/deep

    # T10.5 — parent appears in root listing
    assert_output "nested/" \
        "T10.5 ls shows nested/" \
        "${EXSH[@]}" ls testcol

    # T10.6 — child appears in parent listing
    assert_output "deep/" \
        "T10.6 ls testcol:/nested shows deep/" \
        "${EXSH[@]}" ls testcol:/nested

    # T10.7 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T10.7 mkdir unknown nick fails" \
        "${EXSH[@]}" mkdir ghost:/newdir

    # T10.8 — missing path (no colon)
    assert_output "path is required" \
        "T10.8 mkdir without path fails" \
        "${EXSH[@]}" mkdir testcol
}
