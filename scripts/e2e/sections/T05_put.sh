#!/usr/bin/env bash
# T05 — put (file, stdin, MIME, binary, overwrite, errors)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T05_put() {
    step "T05 — put"

    # Prepare local files (persist for T06+)
    printf '<hello>world</hello>' > "${TMPDIR_E2E}/hello.xml"
    printf '\x00\x01\x02\x03'   > "${TMPDIR_E2E}/data.bin"

    # T05.1 — upload XML from file
    assert_exit0 "T05.1 put XML file" \
        "${EXSH[@]}" put testcol:/hello.xml -f "${TMPDIR_E2E}/hello.xml"

    # T05.2 — silent overwrite
    assert_exit0 "T05.2 put overwrites silently" \
        "${EXSH[@]}" put testcol:/hello.xml -f "${TMPDIR_E2E}/hello.xml"

    # T05.3 — explicit MIME override
    assert_exit0 "T05.3 put with explicit --mime" \
        "${EXSH[@]}" put testcol:/hello.xml -f "${TMPDIR_E2E}/hello.xml" --mime application/xml

    # T05.4 — read from stdin
    local code=0
    _LAST_OUTPUT="$(echo '<from>stdin</from>' | "${EXSH[@]}" put testcol:/stdin.xml 2>&1)" || code=$?
    if [[ $code -eq 0 ]]; then
        ok "T05.4 put from stdin"
    else
        fail "T05.4 put from stdin (expected exit 0, got ${code})"
    fi

    # T05.5 — binary file (MIME guessed as application/octet-stream)
    assert_exit0 "T05.5 put binary file" \
        "${EXSH[@]}" put testcol:/data.bin -f "${TMPDIR_E2E}/data.bin"

    # T05.6 — path traversal rejected
    assert_output "path traversal not allowed" \
        "T05.6 put path traversal rejected" \
        "${EXSH[@]}" put "testcol:/../escape.xml" -f "${TMPDIR_E2E}/hello.xml"

    # T05.7 — missing path (no colon)
    assert_output "path is required" \
        "T05.7 put without path fails" \
        "${EXSH[@]}" put testcol -f "${TMPDIR_E2E}/hello.xml"

    # T05.8 — unreadable local file
    assert_output "cannot read" \
        "T05.8 put non-existent file fails" \
        "${EXSH[@]}" put testcol:/x.xml -f /nonexistent/file.xml

    # T05.9 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T05.9 put unknown nick fails" \
        "${EXSH[@]}" put ghost:/x.xml -f "${TMPDIR_E2E}/hello.xml"

    # T05.10 — eXist auto-creates intermediate collections; verified in T06
    assert_exit0 "T05.10 put to nested path auto-creates parent collections" \
        "${EXSH[@]}" put testcol:/missing/sub/doc.xml -f "${TMPDIR_E2E}/hello.xml"

    # T05.11 — malformed XML is rejected
    printf '<unclosed>' > "${TMPDIR_E2E}/bad.xml"
    assert_output "not well-formed XML" \
        "T05.11 put rejects malformed XML" \
        "${EXSH[@]}" put testcol:/bad.xml -f "${TMPDIR_E2E}/bad.xml"

    # T05.12 — binary file is uploaded without XML validation
    assert_exit0 "T05.12 put binary skips XML validation" \
        "${EXSH[@]}" put testcol:/data.bin -f "${TMPDIR_E2E}/data.bin" --mime application/octet-stream
}
