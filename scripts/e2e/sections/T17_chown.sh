#!/usr/bin/env bash
# T17 — chown (change owner / group of a document or collection)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T17_chown() {
    step "T17 — chown owner / group / recursive"

    # Setup: create a dedicated user, group, collection and documents.
    assert_exit0 "T17 setup: create group e2echowngrp" \
        "${EXSH[@]}" group add e2echowngrp --server localhost
    assert_exit0 "T17 setup: create user e2echownuser in guest group" \
        "${EXSH[@]}" user add e2echownuser --group guest --password "testpass123" --server localhost
    assert_exit0 "T17 setup: create collection chowntest" \
        "${EXSH[@]}" collection add localhost /chowntest --nick chowntest
    assert_exit0 "T17 setup: upload doc.xml" \
        "${EXSH[@]}" put - chowntest:/doc.xml <<< '<root/>'
    assert_exit0 "T17 setup: create subcollection sub" \
        "${EXSH[@]}" mkdir chowntest:/sub
    assert_exit0 "T17 setup: upload sub/child.xml" \
        "${EXSH[@]}" put - chowntest:/sub/child.xml <<< '<child/>'

    # T17.1 — chown owner only
    assert_output "updated" \
        "T17.1 chown owner only succeeds" \
        "${EXSH[@]}" chown admin chowntest:/doc.xml

    # T17.2 — chown group only
    assert_output "updated" \
        "T17.2 chown group only succeeds" \
        "${EXSH[@]}" chown :e2echowngrp chowntest:/doc.xml

    # T17.3 — chown owner and group together
    assert_output "updated" \
        "T17.3 chown owner:group succeeds" \
        "${EXSH[@]}" chown "admin:e2echowngrp" chowntest:/doc.xml

    # T17.4 — chown on a collection (non-recursive)
    assert_output "updated" \
        "T17.4 chown on collection (non-recursive) succeeds" \
        "${EXSH[@]}" chown admin chowntest:/sub

    # T17.5 — chown -R on a collection (recursive, 2 items: /sub + /sub/child.xml)
    assert_output "2 items" \
        "T17.5 chown -R reports item count" \
        "${EXSH[@]}" chown -R admin chowntest:/sub

    # T17.6 — chown on the collection root
    assert_output "updated" \
        "T17.6 chown on collection root path succeeds" \
        "${EXSH[@]}" chown admin chowntest:

    # T17.7 — empty owner spec exits non-zero
    assert_exit1 "T17.7 empty owner spec exits non-zero" \
        "${EXSH[@]}" chown "" chowntest:/doc.xml

    # T17.8 — colon-only spec exits non-zero
    assert_exit1 "T17.8 colon-only spec exits non-zero" \
        "${EXSH[@]}" chown ":" chowntest:/doc.xml

    # T17.9 — unknown user exits non-zero
    assert_exit1 "T17.9 unknown user exits non-zero" \
        "${EXSH[@]}" chown "nosuchuser99" chowntest:/doc.xml

    # T17.10 — unknown group exits non-zero
    assert_exit1 "T17.10 unknown group exits non-zero" \
        "${EXSH[@]}" chown ":nosuchgroup99" chowntest:/doc.xml

    # T17.11 — -R on a document (not a collection) exits non-zero
    assert_exit1 "T17.11 -R on a document exits non-zero" \
        "${EXSH[@]}" chown -R admin chowntest:/doc.xml

    # T17.12 — unknown collection nick exits non-zero
    assert_exit1 "T17.12 unknown collection nick exits non-zero" \
        "${EXSH[@]}" chown admin "ghost:/doc.xml"

    # Cleanup
    assert_exit0 "T17 cleanup: rm sub/child.xml" \
        "${EXSH[@]}" rm chowntest:/sub/child.xml
    assert_exit0 "T17 cleanup: rm doc.xml" \
        "${EXSH[@]}" rm chowntest:/doc.xml
    assert_exit0 "T17 cleanup: rm collection sub" \
        "${EXSH[@]}" collection rm chowntest:/sub
    assert_exit0 "T17 cleanup: collection rm chowntest" \
        "${EXSH[@]}" collection rm chowntest:
    assert_exit0 "T17 cleanup: user rm e2echownuser" \
        "${EXSH[@]}" user rm e2echownuser --yes --server localhost
    assert_exit0 "T17 cleanup: group rm e2echowngrp" \
        "${EXSH[@]}" group rm e2echowngrp --yes --server localhost
}
