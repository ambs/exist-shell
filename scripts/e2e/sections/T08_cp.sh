#!/usr/bin/env bash
# T08 — cp (local→remote, remote→local, remote→remote, trailing slash, directory target, errors)
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

    # T08.11 — remote→local with directory as target: filename taken from remote path
    mkdir -p "${TMPDIR_E2E}/cpdir"
    assert_exit0 "T08.11 cp remote file into local directory" \
        "${EXSH[@]}" cp testcol:/hello.xml "${TMPDIR_E2E}/cpdir"
    if [[ -f "${TMPDIR_E2E}/cpdir/hello.xml" ]]; then
        ok "T08.11 file landed as cpdir/hello.xml"
    else
        fail "T08.11 file landed as cpdir/hello.xml (not found)"
    fi

    # T08.12 — remote→local: remote source does not exist (404 → not found in collection)
    assert_output "not found in collection" \
        "T08.12 cp non-existent remote source fails" \
        "${EXSH[@]}" cp testcol:/nonexistent.xml "${TMPDIR_E2E}/out.xml"

    # T08.13 — remote→local: local destination is unwritable (/dev/null/out.xml is never writable)
    assert_output "cannot write" \
        "T08.13 cp to unwritable local path fails" \
        "${EXSH[@]}" cp testcol:/hello.xml /dev/null/out.xml

    # T08.14-15 — cp remote .xq resource to local: raw source bytes, byte-for-byte
    # (regression: #141/#144)
    assert_exit0 "T08.14 cp remote .xq file to local" \
        "${EXSH[@]}" cp testcol:/script.xq "${TMPDIR_E2E}/script_dl.xq"
    if cmp -s "${TMPDIR_E2E}/script.xq" "${TMPDIR_E2E}/script_dl.xq"; then
        ok "T08.15 downloaded .xq file matches original bytes exactly"
    else
        _LAST_OUTPUT="downloaded .xq file differs from original"
        fail "T08.15 downloaded .xq file matches original bytes exactly"
    fi

    # ---------------------------------------------------------------------------
    # T08.16-18 — is_remote no longer misclassifies colon-containing local
    # paths as nick:path targets (#138)
    # ---------------------------------------------------------------------------

    # T08.16 — a fake Windows-style source (drive letter + backslash) is now
    # treated as local, not as a nick lookup. It fails as a local read error
    # rather than "collection 'C' not found".
    assert_output "cannot read" \
        "T08.16 cp with Windows-style source is treated as local, not a nick" \
        "${EXSH[@]}" cp 'C:\data\doc.xml' testcol:/should_not_upload.xml

    # T08.17 — a relative local path with a directory component before the
    # colon (e.g. a filename containing ':') is treated as local and uploads
    # successfully instead of being misread as nick:path.
    mkdir -p "${TMPDIR_E2E}/colon_dir"
    printf '<colon>ok</colon>' > "${TMPDIR_E2E}/colon_dir/name:v1.xml"
    assert_exit0 "T08.17 cp local path with colon in a path component uploads" \
        "${EXSH[@]}" cp "${TMPDIR_E2E}/colon_dir/name:v1.xml" testcol:/colon_upload.xml

    assert_output "<colon>ok</colon>" \
        "T08.18 uploaded colon-named file content is intact" \
        "${EXSH[@]}" cat testcol:/colon_upload.xml
}
