#!/usr/bin/env bash
# T02 — server add / server ls / server rm / server rename
# Sourced by scripts/e2e.sh — do not execute directly.

section_T02_server() {
    step "T02 — server add / server ls / server rm / server rename"

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

    # ---------------------------------------------------------------------------
    # server rm
    # ---------------------------------------------------------------------------

    # T02.10 — add local3 as a disposable third alias for the same server
    assert_output "Server 'local3' added." \
        "T02.10 server add local3 (disposable nick for rm tests)" \
        "${EXSH[@]}" server add localhost --user admin --password "" --nick local3

    # T02.11 — add a collection on local3 to test cascade removal
    assert_output "Collection 'col3' added." \
        "T02.11 collection add col3@local3 (to cascade-remove with local3)" \
        "${EXSH[@]}" collection add testcol@local3 --nick col3

    # T02.12 — rm local3: collection col3 also removed (single run, two checks)
    _run "${EXSH[@]}" server rm local3
    assert_in_last "Also removed 1 collection: col3." "T02.12 server rm reports cascade removal of col3"
    assert_in_last "Server 'local3' removed." "T02.12 server rm removes local3"

    # T02.13 — server ls no longer shows local3
    assert_output_absent "local3" \
        "T02.13 server ls no longer shows local3" \
        "${EXSH[@]}" server ls

    # T02.14 — collection ls no longer shows col3 (cascade verified)
    assert_output_absent "col3" \
        "T02.14 collection ls no longer shows col3 after cascade" \
        "${EXSH[@]}" collection ls

    # T02.15 — unknown nick is rejected
    assert_output "server nick 'ghost' not found" \
        "T02.15 server rm unknown nick fails" \
        "${EXSH[@]}" server rm ghost

    # T02.16 — remove local2 to leave a single server (setup for auto-select test)
    assert_output "Server 'local2' removed." \
        "T02.16 server rm local2 (leaves only localhost)" \
        "${EXSH[@]}" server rm local2

    # T02.17 — collection add without @server auto-selects the sole remaining server
    assert_output "Collection 'temptest' added." \
        "T02.17 collection add auto-selects sole server when no @server given" \
        "${EXSH[@]}" collection add testcol --nick temptest

    # T02.18 — cleanup: remove temptest so T03 starts with no collections registered
    assert_output "Collection 'temptest' removed." \
        "T02.18 collection rm temptest (cleanup)" \
        "${EXSH[@]}" collection rm temptest

    # T02.19 — restore local2 so T03 preconditions hold (two servers required)
    assert_output "Server 'local2' added." \
        "T02.19 re-add local2 (restore T03 precondition)" \
        "${EXSH[@]}" server add localhost --user admin --password "" --nick local2

    # ---------------------------------------------------------------------------
    # server rename
    # ---------------------------------------------------------------------------

    # T02.20 — add a disposable nick to rename
    assert_output "Server 'renametest' added." \
        "T02.20 server add renametest (for rename tests)" \
        "${EXSH[@]}" server add localhost --user admin --password "" --nick renametest

    # T02.21 — register a collection on renametest to verify cascade update
    assert_output "Collection 'renamecol' added." \
        "T02.21 collection add renamecol@renametest (to verify cascade update)" \
        "${EXSH[@]}" collection add testcol@renametest --nick renamecol

    # T02.22 — rename renametest → newname; collection reference updated
    _run "${EXSH[@]}" server rename renametest newname
    assert_in_last "Also updated 1 collection: renamecol." \
        "T02.22 server rename reports cascade update of renamecol"
    assert_in_last "Server 'renametest' renamed to 'newname'." \
        "T02.22 server rename success message"

    # T02.23 — server ls shows newname, not renametest
    assert_output "newname" \
        "T02.23 server ls shows newname" \
        "${EXSH[@]}" server ls
    assert_output_absent "renametest" \
        "T02.23 server ls no longer shows renametest" \
        "${EXSH[@]}" server ls

    # T02.24 — collection ls shows renamecol pointing to @newname
    assert_output "@newname" \
        "T02.24 collection ls shows renamecol with updated server nick" \
        "${EXSH[@]}" collection ls

    # T02.25 — rename unknown nick fails
    assert_output "server nick 'ghost' not found" \
        "T02.25 server rename unknown nick fails" \
        "${EXSH[@]}" server rename ghost newname2

    # T02.26 — rename to a nick that already exists fails
    assert_output "server nick 'localhost' already exists" \
        "T02.26 server rename to existing nick fails" \
        "${EXSH[@]}" server rename newname localhost

    # T02.27 — rename to the same nick fails
    assert_output "same as the old nick" \
        "T02.27 server rename same nick fails" \
        "${EXSH[@]}" server rename newname newname

    # T02.28 — rename to an invalid nick fails
    assert_output "not a valid server nick" \
        "T02.28 server rename invalid new nick fails" \
        "${EXSH[@]}" server rename newname "invalid!"

    # T02.29 — cleanup: rm newname (also cascade-removes renamecol)
    assert_output "Server 'newname' removed." \
        "T02.29 server rm newname (cleanup; renamecol cascade-removed)" \
        "${EXSH[@]}" server rm newname

    # ---------------------------------------------------------------------------
    # server status / ping
    # ---------------------------------------------------------------------------

    # T02.30 — status of one server: URL, version, and OK with latency (single run)
    _run "${EXSH[@]}" server status localhost
    assert_in_last "Server:   http://localhost:8080/exist" "T02.30 server status shows URL"
    assert_in_last "Version:  " "T02.30 server status shows version"
    assert_in_last "Status:   OK (" "T02.30 server status reports OK with latency"

    # T02.31 — top-level ping alias exits 0
    assert_exit0 "T02.31 ping alias exits 0" \
        "${EXSH[@]}" ping localhost

    # T02.32 — no nick: every configured server checked, one row each
    _run "${EXSH[@]}" server status
    assert_in_last "localhost" "T02.32 status sweep lists localhost"
    assert_in_last "local2" "T02.32 status sweep lists local2"
    assert_in_last "OK (" "T02.32 status sweep reports OK"

    # T02.33 — unknown nick exits 1
    assert_exit1 "T02.33 server status unknown nick exits non-zero" \
        "${EXSH[@]}" server status ghost
}
