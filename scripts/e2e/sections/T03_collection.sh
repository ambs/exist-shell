#!/usr/bin/env bash
# T03 — collection add / collection ls / collection rm
# Sourced by scripts/e2e.sh — do not execute directly.

section_T03_collection() {
    step "T03 — collection add / collection ls / collection rm"

    # T03.1 — add a collection specifying the server explicitly
    assert_output "Collection 'testcol' added." \
        "T03.1 collection add (explicit server)" \
        "${EXSH[@]}" collection add testcol@localhost

    # T03.2 — list shows the registered collection
    assert_output "/db/testcol" \
        "T03.2 collection ls shows path" \
        "${EXSH[@]}" collection ls
    assert_output "@localhost" \
        "T03.2 collection ls shows server nick" \
        "${EXSH[@]}" collection ls

    # T03.3 — duplicate nick is rejected
    assert_output "already exists" \
        "T03.3 collection add duplicate nick fails" \
        "${EXSH[@]}" collection add testcol@localhost

    # T03.4 — same collection registered under a different nick
    assert_output "Collection 'testcol2' added." \
        "T03.4 collection add same collection different nick" \
        "${EXSH[@]}" collection add testcol@localhost --nick testcol2

    # T03.5 — both entries appear in ls
    assert_output "testcol" \
        "T03.5 collection ls shows original entry" \
        "${EXSH[@]}" collection ls
    assert_output "testcol2" \
        "T03.5 collection ls shows new nick" \
        "${EXSH[@]}" collection ls

    # T03.6 — collection that does not exist on the server is rejected
    assert_output "not found on server" \
        "T03.6 collection add nonexistent collection fails" \
        "${EXSH[@]}" collection add nonexistent@localhost

    # T03.7 — unknown server nick is rejected
    assert_output "not found" \
        "T03.7 collection add unknown server nick fails" \
        "${EXSH[@]}" collection add testcol@ghost

    # T03.8 — no server specified with multiple servers configured
    assert_output "--server is required" \
        "T03.8 collection add without server fails when multiple servers exist" \
        "${EXSH[@]}" collection add testcol

    # T03.9 — conflicting @server in argument and --server flag
    assert_output "conflicting" \
        "T03.9 collection add conflicting server specs fails" \
        "${EXSH[@]}" collection add testcol@localhost --server local2

    # T03.11 — add a disposable alias nick for removal tests
    assert_output "Collection 'rmtest' added." \
        "T03.11 collection add rmtest alias" \
        "${EXSH[@]}" collection add testcol@localhost --nick rmtest

    # T03.12 — rm removes the config entry (no --delete: server collection untouched)
    assert_output "Collection 'rmtest' removed." \
        "T03.12 collection rm removes config entry" \
        "${EXSH[@]}" collection rm rmtest

    # T03.13 — ls no longer shows rmtest
    assert_output_absent "rmtest" \
        "T03.13 collection ls no longer shows rmtest" \
        "${EXSH[@]}" collection ls
}
