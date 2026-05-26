#!/usr/bin/env bash
# T16 — group ls / group add / group rm
# Sourced by scripts/e2e.sh — do not execute directly.

section_T16_group() {
    step "T16 — group ls / group add / group rm"

    # T16.1 — group ls lists built-in groups (dba and guest always exist)
    assert_output "dba" \
        "T16.1 group ls lists dba group" \
        "${EXSH[@]}" group ls --server localhost
    assert_in_last "guest" \
        "T16.1 group ls lists guest group"

    # T16.2 — admin appears as a member of the dba group
    assert_output "admin" \
        "T16.2 group ls shows admin in dba group" \
        "${EXSH[@]}" group ls --server localhost

    # T16.3 — group add creates a new group
    assert_output "Group 'e2egroup' created." \
        "T16.3 group add creates e2egroup" \
        "${EXSH[@]}" group add e2egroup --server localhost

    # T16.4 — group ls shows the newly created group
    assert_output "e2egroup" \
        "T16.4 group ls shows e2egroup after creation" \
        "${EXSH[@]}" group ls --server localhost

    # T16.5 — group add with @server syntax
    assert_output "Group 'e2egroup2' created." \
        "T16.5 group add with @server syntax" \
        "${EXSH[@]}" group add e2egroup2@localhost

    # T16.6 — group ls with @server syntax
    assert_output "e2egroup2" \
        "T16.6 group ls with @server syntax" \
        "${EXSH[@]}" group ls @localhost

    # T16.7 — group rm removes the group (--yes skips confirmation)
    assert_output "Group 'e2egroup2' removed." \
        "T16.7 group rm removes e2egroup2" \
        "${EXSH[@]}" group rm e2egroup2 --yes --server localhost
    assert_output_absent "e2egroup2" \
        "T16.7 group ls no longer shows e2egroup2" \
        "${EXSH[@]}" group ls --server localhost

    # T16.8 — group rm with @server syntax
    assert_output "Group 'e2egroup' removed." \
        "T16.8 group rm with @server syntax" \
        "${EXSH[@]}" group rm e2egroup@localhost --yes

    # T16.9 — group ls no longer shows e2egroup
    assert_output_absent "e2egroup" \
        "T16.9 group ls no longer shows e2egroup after removal" \
        "${EXSH[@]}" group ls --server localhost

    # T16.10 — group add for a group that already exists exits non-zero
    local code=0
    _run "${EXSH[@]}" group add dba --server localhost || code=$?
    if [[ $code -ne 0 ]]; then
        ok "T16.10 group add for existing group exits non-zero"
    else
        fail "T16.10 group add for existing group (expected exit != 0, got 0)"
    fi
}
