#!/usr/bin/env bash
# T18 — chmod (change POSIX permissions on a document or collection)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T18_chmod() {
    step "T18 — chmod (POSIX permissions)"

    # Setup: create a dedicated collection, documents, and a subcollection.
    assert_exit0 "T18 setup: create collection chmodtest" \
        "${EXSH[@]}" collection new chmodtest@localhost
    assert_exit0 "T18 setup: upload doc.xml" \
        "${EXSH[@]}" put chmodtest:/doc.xml -f /dev/stdin <<< '<root/>'
    assert_exit0 "T18 setup: create subcollection sub" \
        "${EXSH[@]}" mkdir chmodtest:/sub
    assert_exit0 "T18 setup: upload sub/child.xml" \
        "${EXSH[@]}" put chmodtest:/sub/child.xml -f /dev/stdin <<< '<child/>'

    # T18.1 — octal chmod on a document
    assert_output "updated" \
        "T18.1 octal chmod 0644 on a document succeeds" \
        "${EXSH[@]}" chmod 0644 chmodtest:/doc.xml

    # T18.2 — verify permissions reflected in ls output
    assert_output "rw-r--r--" \
        "T18.2 ls shows rw-r--r-- (0644) after chmod" \
        "${EXSH[@]}" ls chmodtest:

    # T18.3 — symbolic chmod u+x on a document
    assert_output "updated" \
        "T18.3 symbolic chmod u+x on a document succeeds" \
        "${EXSH[@]}" chmod u+x chmodtest:/doc.xml

    # T18.4 — verify u+x was applied: rw-r--r-- (0644) + u+x → rwxr--r-- (0744)
    assert_output "rwxr--r--" \
        "T18.4 ls shows rwxr--r-- (0744) after u+x" \
        "${EXSH[@]}" ls chmodtest:

    # T18.5 — symbolic chmod go-r removes group and other read
    assert_output "updated" \
        "T18.5 symbolic chmod go-r succeeds" \
        "${EXSH[@]}" chmod go-r chmodtest:/doc.xml

    # T18.6 — symbolic chmod a=rw sets absolute mode for all
    assert_output "updated" \
        "T18.6 symbolic chmod a=rw succeeds" \
        "${EXSH[@]}" chmod a=rw chmodtest:/doc.xml

    # T18.7 — verify a=rw → rw-rw-rw- (0666)
    assert_output "rw-rw-rw-" \
        "T18.7 ls shows rw-rw-rw- (0666) after a=rw" \
        "${EXSH[@]}" ls chmodtest:

    # T18.8 — octal chmod on a collection (non-recursive)
    assert_output "updated" \
        "T18.8 octal chmod on a collection (non-recursive) succeeds" \
        "${EXSH[@]}" chmod 0755 chmodtest:/sub

    # T18.9 — recursive chmod (2 items: /sub + /sub/child.xml)
    assert_output "2 items" \
        "T18.9 recursive chmod -R reports item count" \
        "${EXSH[@]}" chmod -R 0644 chmodtest:/sub

    # T18.10 — chmod on the collection root
    assert_output "updated" \
        "T18.10 chmod on collection root succeeds" \
        "${EXSH[@]}" chmod 0755 chmodtest:

    # T18.11 — mode without leading zero is still valid octal
    assert_output "updated" \
        "T18.11 chmod 755 (no leading zero) is accepted" \
        "${EXSH[@]}" chmod 755 chmodtest:/doc.xml

    # T18.12 — invalid mode (digit 9 is not octal) exits non-zero
    assert_exit1 "T18.12 chmod 0999 exits non-zero (invalid mode)" \
        "${EXSH[@]}" chmod 0999 chmodtest:/doc.xml

    # T18.13 — -R on a document (not a collection) exits non-zero
    assert_exit1 "T18.13 -R on a document exits non-zero" \
        "${EXSH[@]}" chmod -R 0644 chmodtest:/doc.xml

    # T18.14 — unknown collection nick exits non-zero
    assert_exit1 "T18.14 unknown collection nick exits non-zero" \
        "${EXSH[@]}" chmod 0644 ghost:/doc.xml

    # Cleanup
    assert_exit0 "T18 cleanup: collection rm chmodtest --delete" \
        "${EXSH[@]}" collection rm chmodtest --delete
}
