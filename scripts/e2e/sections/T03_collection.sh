#!/usr/bin/env bash
# T03 — collection add / collection new / collection ls / collection rm
# Sourced by scripts/e2e.sh — do not execute directly.

section_T03_collection() {
    step "T03 — collection add / collection new / collection ls / collection rm"

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

    # T03.14 — rm unknown nick fails
    assert_output "collection 'ghost' not found" \
        "T03.14 collection rm unknown nick fails" \
        "${EXSH[@]}" collection rm ghost

    # T03.15 — setup for --delete test: create /db/rmcol on server and register it
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/octet-stream" \
        --data-binary "" \
        "${EXIST_URL}/db/rmcol/.keep" >/dev/null
    curl -sf -u "${ADMIN_AUTH}" -X DELETE "${EXIST_URL}/db/rmcol/.keep" >/dev/null
    assert_output "Collection 'rmcol' added." \
        "T03.15 setup: /db/rmcol created on server and registered" \
        "${EXSH[@]}" collection add rmcol@localhost

    # T03.16 — rm --delete removes from config and deletes the server collection
    assert_output "Collection 'rmcol' removed." \
        "T03.16 collection rm --delete removes config entry and server collection" \
        "${EXSH[@]}" collection rm rmcol --delete

    # T03.17 — verify /db/rmcol is actually gone from the server
    local _status
    _status="$(curl -s -o /dev/null -w "%{http_code}" -u "${ADMIN_AUTH}" "${EXIST_URL}/db/rmcol")"
    if [[ "${_status}" == "404" ]]; then
        ok "T03.17 /db/rmcol returns 404 after --delete"
    else
        fail "T03.17 /db/rmcol returns 404 after --delete (got HTTP ${_status})"
    fi

    # T03.18 — --delete when server collection already gone: exit 1, config unchanged
    # Create /db/rmcol2, register it, then delete it from the server behind exsh's back
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/octet-stream" \
        --data-binary "" \
        "${EXIST_URL}/db/rmcol2/.keep" >/dev/null
    curl -sf -u "${ADMIN_AUTH}" -X DELETE "${EXIST_URL}/db/rmcol2/.keep" >/dev/null
    assert_exit0 "T03.18 setup: register rmcol2" \
        "${EXSH[@]}" collection add rmcol2@localhost
    curl -sf -u "${ADMIN_AUTH}" -X DELETE "${EXIST_URL}/db/rmcol2" >/dev/null
    assert_output "not found on server" \
        "T03.18 collection rm --delete fails when server collection already gone" \
        "${EXSH[@]}" collection rm rmcol2 --delete

    # T03.19 — config-only cleanup: rmcol2 entry was preserved by T03.18 failure
    assert_output "Collection 'rmcol2' removed." \
        "T03.19 collection rm rmcol2 (config-only cleanup of dangling entry)" \
        "${EXSH[@]}" collection rm rmcol2

    # T03.20 — rm --delete on a non-empty collection: eXist deletes recursively
    curl -sf -u "${ADMIN_AUTH}" -X PUT \
        -H "Content-Type: application/xml" \
        --data-binary '<doc/>' \
        "${EXIST_URL}/db/rmfull/doc.xml" >/dev/null
    assert_output "Collection 'rmfull' added." \
        "T03.20 setup: /db/rmfull with a document created and registered" \
        "${EXSH[@]}" collection add rmfull@localhost
    assert_output "Collection 'rmfull' removed." \
        "T03.20 collection rm --delete removes non-empty collection" \
        "${EXSH[@]}" collection rm rmfull --delete
    local _rmfull_status
    _rmfull_status="$(curl -s -o /dev/null -w "%{http_code}" -u "${ADMIN_AUTH}" "${EXIST_URL}/db/rmfull")"
    if [[ "${_rmfull_status}" == "404" ]]; then
        ok "T03.20 /db/rmfull returns 404 after --delete (non-empty collection deleted recursively)"
    else
        fail "T03.20 /db/rmfull returns 404 after --delete (non-empty collection deleted recursively) (got HTTP ${_rmfull_status})"
    fi

    # T03.21 — collection new creates /db/newcol on the server and registers it
    assert_output "Collection 'newcol' created at /db/newcol." \
        "T03.21 collection new creates collection and registers it" \
        "${EXSH[@]}" collection new newcol@localhost
    assert_output "newcol" \
        "T03.21 collection ls shows newcol" \
        "${EXSH[@]}" collection ls

    # T03.22 — verify /db/newcol was actually created on the server
    local _newcol_status
    _newcol_status="$(curl -s -o /dev/null -w "%{http_code}" -u "${ADMIN_AUTH}" "${EXIST_URL}/db/newcol")"
    if [[ "${_newcol_status}" == "200" ]]; then
        ok "T03.22 /db/newcol returns 200 after collection new"
    else
        fail "T03.22 /db/newcol returns 200 after collection new (got HTTP ${_newcol_status})"
    fi

    # T03.23 — collection already exists on server: prints message, exits 0, config unchanged
    assert_output "already exists" \
        "T03.23 collection new on existing server collection exits 0 with message" \
        "${EXSH[@]}" collection new newcol@localhost --nick newalias
    assert_output_absent "newalias" \
        "T03.23 newalias not added to config when collection already exists" \
        "${EXSH[@]}" collection ls

    # T03.24 — collection new with --nick registers under a custom nickname
    assert_output "Collection 'nc2' created at /db/newcol2." \
        "T03.24 collection new --nick uses custom nickname" \
        "${EXSH[@]}" collection new newcol2@localhost --nick nc2
    assert_output "nc2" \
        "T03.24 collection ls shows nc2" \
        "${EXSH[@]}" collection ls
    assert_output "/db/newcol2" \
        "T03.24 collection ls shows /db/newcol2 path for nc2" \
        "${EXSH[@]}" collection ls

    # T03.25 — config-only cleanup so T04+ start without extra nicks
    assert_output "Collection 'newcol' removed." \
        "T03.25 cleanup: rm newcol" \
        "${EXSH[@]}" collection rm newcol
    assert_output "Collection 'nc2' removed." \
        "T03.25 cleanup: rm nc2" \
        "${EXSH[@]}" collection rm nc2
}
