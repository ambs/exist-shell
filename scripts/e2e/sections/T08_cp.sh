#!/usr/bin/env bash
# T08 — cp (local→remote, remote→local, remote→remote, trailing slash, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T08_cp() {
    step "T08 — cp"

    # T08.1 — local→remote
    assert_exit0 "T08.1 cp local file to remote" \
        "${EXSH[@]}" cp "${TMPDIR_E2E}/hello.xml" testcol:/hello_copy.xml

    # T08.2 — verify remote file appears in listing
    assert_output "hello_copy.xml" \
        "T08.2 ls shows uploaded hello_copy.xml" \
        "${EXSH[@]}" ls testcol

    # T08.3 — remote→local
    assert_exit0 "T08.3 cp remote file to local" \
        "${EXSH[@]}" cp testcol:/hello.xml "${TMPDIR_E2E}/hello_dl.xml"

    # T08.4 — verify downloaded file content
    local actual
    actual="$(cat "${TMPDIR_E2E}/hello_dl.xml")"
    if echo "${actual}" | grep -qF "<hello>world</hello>"; then
        ok "T08.4 downloaded file contains expected content"
    else
        _LAST_OUTPUT="${actual}"
        fail "T08.4 downloaded file contains expected content"
    fi

    # T08.5 — remote→remote (testcol and testcol2 both point to /db/testcol)
    assert_exit0 "T08.5 cp remote to remote" \
        "${EXSH[@]}" cp testcol:/hello.xml testcol2:/hello_r2r.xml

    # T08.6 — verify remote→remote result appears in listing
    assert_output "hello_r2r.xml" \
        "T08.6 ls shows hello_r2r.xml after remote-to-remote copy" \
        "${EXSH[@]}" ls testcol

    # T08.7 — trailing slash on remote target resolves to source filename
    assert_exit0 "T08.7 cp to remote trailing-slash target" \
        "${EXSH[@]}" cp "${TMPDIR_E2E}/hello.xml" "testcol:/"

    # T08.8 — both paths local
    assert_output "at least one of source or target" \
        "T08.8 cp both local fails" \
        "${EXSH[@]}" cp "${TMPDIR_E2E}/hello.xml" "${TMPDIR_E2E}/copy.xml"

    # T08.9 — unreadable local source
    assert_output "cannot read" \
        "T08.9 cp non-existent local source fails" \
        "${EXSH[@]}" cp /nonexistent/file.xml testcol:/nope.xml

    # T08.10 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T08.10 cp unknown nick fails" \
        "${EXSH[@]}" cp ghost:/hello.xml "${TMPDIR_E2E}/x.xml"
}
