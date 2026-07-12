#!/usr/bin/env bash
# T19 — find (XPath expression search, with --remove)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T19_find() {
    step "T19 — find"

    # Fixtures: one document matches the predicate, one does not.
    printf '<foo type="draft"><title>Draft doc</title></foo>' > "${TMPDIR_E2E}/find_a.xml"
    printf '<foo type="final"><title>Final doc</title></foo>' > "${TMPDIR_E2E}/find_b.xml"
    assert_exit0 "T19.0a put find_a.xml (matches predicate)" \
        "${EXSH[@]}" put testcol:/find_a.xml -f "${TMPDIR_E2E}/find_a.xml"
    assert_exit0 "T19.0b put find_b.xml (does not match predicate)" \
        "${EXSH[@]}" put testcol:/find_b.xml -f "${TMPDIR_E2E}/find_b.xml"

    # T19.1 — list mode finds only the matching document
    assert_output "testcol:/find_a.xml" \
        "T19.1 find lists the matching document" \
        "${EXSH[@]}" find testcol:/ --query 'foo[@type="draft"]'
    assert_output_absent "find_b.xml" \
        "T19.1 find does not list the non-matching document" \
        "${EXSH[@]}" find testcol:/ --query 'foo[@type="draft"]'

    # T19.2 — a predicate matching nothing produces no output
    assert_empty_output "T19.2 find with no matches prints nothing" \
        "${EXSH[@]}" find testcol:/ --query 'foo[@type="nonexistent"]'

    # T19.3 — --remove --yes deletes the match and prints what was removed
    assert_output "testcol:/find_a.xml" \
        "T19.3 find --remove --yes prints the removed document" \
        "${EXSH[@]}" find testcol:/ --query 'foo[@type="draft"]' --remove --yes

    # T19.4 — follow-up ls no longer shows the removed file
    assert_output_absent "find_a.xml" \
        "T19.4 ls no longer shows find_a.xml after removal" \
        "${EXSH[@]}" ls testcol

    # T19.5 — --remove --yes with zero matches is a no-op
    assert_empty_output "T19.5 find --remove --yes with no matches is a no-op" \
        "${EXSH[@]}" find testcol:/ --query 'foo[@type="draft"]' --remove --yes
    assert_output "find_b.xml" \
        "T19.5 find_b.xml still present (nothing removed)" \
        "${EXSH[@]}" ls testcol

    # T19.6 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T19.6 find unknown nick fails" \
        "${EXSH[@]}" find ghost:/ --query 'foo[@type="draft"]'

    # T19.6b — known collection but a path that does not exist reports "not found"
    #          (rather than silently returning zero matches)
    assert_output "not found" \
        "T19.6b find nonexistent path fails" \
        "${EXSH[@]}" find testcol:/no_such_subcollection --query 'foo[@type="draft"]'

    # T19.7 — malformed expression surfaces the server's XQuery error
    assert_output "XQuery error" \
        "T19.7 find malformed expression rejected by server" \
        "${EXSH[@]}" find testcol:/ --query 'this is not valid !!!'

    # T19.8 — missing --query option
    assert_exit1 "T19.8 find without --query fails" \
        "${EXSH[@]}" find testcol:/

    # Cleanup: remove the remaining fixture so it doesn't affect later runs.
    assert_exit0 "T19.9 cleanup: rm find_b.xml" \
        "${EXSH[@]}" rm testcol:/find_b.xml
}
