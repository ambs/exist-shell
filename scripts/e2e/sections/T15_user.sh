#!/usr/bin/env bash
# T15 — user ls / user add / user rm / user info
# Sourced by scripts/e2e.sh — do not execute directly.

section_T15_user() {
    step "T15 — user ls / user add / user rm / user info"

    # T15.1 — user ls lists built-in accounts (admin and guest always exist)
    assert_output "admin" \
        "T15.1 user ls lists admin account" \
        "${EXSH[@]}" user ls --server localhost
    assert_in_last "guest" \
        "T15.1 user ls lists guest account"

    # T15.2 — admin belongs to the dba group
    assert_output "dba" \
        "T15.2 user ls shows dba group for admin" \
        "${EXSH[@]}" user ls --server localhost

    # T15.3 — user add creates a new account
    assert_output "User 'e2euser' created." \
        "T15.3 user add creates e2euser" \
        "${EXSH[@]}" user add e2euser --group guest --password "testpass123" --server localhost

    # T15.4 — user ls shows the newly created account
    assert_output "e2euser" \
        "T15.4 user ls shows e2euser after creation" \
        "${EXSH[@]}" user ls --server localhost

    # T15.5 — user info shows correct details for e2euser
    assert_output "e2euser" \
        "T15.5 user info shows username" \
        "${EXSH[@]}" user info e2euser --server localhost
    assert_in_last "guest" \
        "T15.5 user info shows group"

    # T15.6 — user info for the built-in admin account
    _run "${EXSH[@]}" user info admin --server localhost
    assert_in_last "admin" "T15.6 user info admin shows username"
    assert_in_last "dba"   "T15.6 user info admin shows dba group"

    # T15.7 — user add with multiple comma-separated groups
    assert_output "User 'e2emulti' created." \
        "T15.7 user add with multiple groups" \
        "${EXSH[@]}" user add e2emulti --group "guest,dba" --password "testpass123" --server localhost
    assert_output "e2emulti" \
        "T15.7 user ls shows e2emulti" \
        "${EXSH[@]}" user ls --server localhost

    # T15.8 — user rm removes the account (--yes skips confirmation)
    assert_output "User 'e2emulti' removed." \
        "T15.8 user rm removes e2emulti" \
        "${EXSH[@]}" user rm e2emulti --yes --server localhost
    assert_output_absent "e2emulti" \
        "T15.8 user ls no longer shows e2emulti" \
        "${EXSH[@]}" user ls --server localhost

    # T15.9 — user info for a non-existent account exits non-zero
    local code=0
    _run "${EXSH[@]}" user info nonexistentuser --server localhost || code=$?
    if [[ $code -ne 0 ]]; then
        ok "T15.9 user info for unknown account exits non-zero"
    else
        fail "T15.9 user info for unknown account (expected exit != 0, got 0)"
    fi

    # T15.10 — user ls with @server syntax
    assert_output "admin" \
        "T15.10 user ls with @server syntax" \
        "${EXSH[@]}" user ls @localhost

    # T15.11 — user add with @server syntax
    assert_output "User 'e2eatuser' created." \
        "T15.11 user add with @server syntax" \
        "${EXSH[@]}" user add e2eatuser@localhost --password "testpass123"

    # T15.12 — user info with @server syntax
    assert_output "e2eatuser" \
        "T15.12 user info with @server syntax" \
        "${EXSH[@]}" user info e2eatuser@localhost

    # T15.13 — user rm with @server syntax
    assert_output "User 'e2eatuser' removed." \
        "T15.13 user rm with @server syntax" \
        "${EXSH[@]}" user rm e2eatuser@localhost --yes

    # T15.14 — cleanup: remove e2euser
    assert_output "User 'e2euser' removed." \
        "T15.14 user rm removes e2euser (cleanup)" \
        "${EXSH[@]}" user rm e2euser --yes --server localhost
    assert_output_absent "e2euser" \
        "T15.14 user ls no longer shows e2euser" \
        "${EXSH[@]}" user ls --server localhost
}
