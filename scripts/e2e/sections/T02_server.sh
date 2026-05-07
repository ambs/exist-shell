#!/usr/bin/env bash
# T02 — server add / server ls
# Sourced by scripts/e2e.sh — do not execute directly.

section_T02_server() {
    step "T02 — server add / server ls"

    # T02.1 — add a valid server
    assert_output "Server 'localhost' added." \
        "T02.1 server add (valid credentials)" \
        "${EXSH[@]}" server add localhost --user admin --password ""

    # T02.2 — list shows the registered server
    assert_output "admin@localhost:8080" \
        "T02.2 server ls lists registered server" \
        "${EXSH[@]}" server ls

    # T02.3 — duplicate nick is rejected
    assert_output "already exists" \
        "T02.3 server add duplicate nick fails" \
        "${EXSH[@]}" server add localhost --user admin --password ""

    # T02.4 — wrong password is rejected after connectivity check
    assert_output "authentication failed" \
        "T02.4 server add wrong password fails" \
        "${EXSH[@]}" server add localhost --user admin --password "wrong" --nick badauth

    # T02.5 — non-existent hostname fails with connection error
    assert_output "Cannot connect to" \
        "T02.5 server add unknown hostname fails" \
        "${EXSH[@]}" server add doesnotexist.local --user admin --password "" --nick ghost

    # T02.6 — correct host, wrong port fails with connection error
    assert_output "Cannot connect to" \
        "T02.6 server add wrong port fails" \
        "${EXSH[@]}" server add localhost --port 9999 --user admin --password "" --nick wrongport

    # T02.7 — failed adds left no trace; original server still the only one
    assert_output "admin@localhost:8080" \
        "T02.7 server ls unchanged after failed adds" \
        "${EXSH[@]}" server ls

    # T02.8 — same server registered under a different nick
    assert_output "Server 'local2' added." \
        "T02.8 server add same host different nick" \
        "${EXSH[@]}" server add localhost --user admin --password "" --nick local2

    # T02.9 — both entries appear in ls
    assert_output "localhost" \
        "T02.9 server ls shows original entry" \
        "${EXSH[@]}" server ls
    assert_output "local2" \
        "T02.9 server ls shows new nick" \
        "${EXSH[@]}" server ls
}
