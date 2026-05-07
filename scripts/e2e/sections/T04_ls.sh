#!/usr/bin/env bash
# T04 — ls (empty collection, error cases)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T04_ls() {
    step "T04 — ls (empty collection, error cases)"

    # T04.1 — empty collection, implicit root path
    assert_empty_output \
        "T04.1 ls empty collection (implicit root)" \
        "${EXSH[@]}" ls testcol

    # T04.2 — empty collection, explicit root path
    assert_empty_output \
        "T04.2 ls empty collection (explicit root)" \
        "${EXSH[@]}" ls testcol:/

    # T04.3 — non-existent subpath
    assert_output "not found in collection" \
        "T04.3 ls non-existent path fails" \
        "${EXSH[@]}" ls testcol:/nonexistent

    # T04.4 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T04.4 ls unknown nick fails" \
        "${EXSH[@]}" ls ghost

    # T04.5 — unknown nick with explicit path
    assert_output "collection 'ghost' not found" \
        "T04.5 ls unknown nick with path fails" \
        "${EXSH[@]}" ls ghost:/some/path
}
