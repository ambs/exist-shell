#!/usr/bin/env bash
# T06 — ls (after uploads)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T06_ls_after() {
    step "T06 — ls (after uploads)"

    # T06.1-4 — root listing contains all uploaded files and the auto-created subcollection
    _run "${EXSH[@]}" ls testcol
    assert_in_last "hello.xml" "T06.1 ls testcol shows hello.xml"
    assert_in_last "stdin.xml" "T06.2 ls testcol shows stdin.xml"
    assert_in_last "data.bin"  "T06.3 ls testcol shows data.bin"
    assert_in_last "missing/"  "T06.4 ls testcol shows auto-created 'missing' subcollection"

    # T06.5 — nested subcollection
    assert_output "sub/" \
        "T06.5 ls testcol:/missing shows 'sub'" \
        "${EXSH[@]}" ls testcol:/missing

    # T06.6 — document inside nested subcollection
    assert_output "doc.xml" \
        "T06.6 ls testcol:/missing/sub shows doc.xml" \
        "${EXSH[@]}" ls testcol:/missing/sub

    # T06.7 — ls on a document path: eXist returns the document body (200); XML parses
    # successfully but has no exist: namespace elements, so the listing is empty — exit 0
    assert_exit0 "T06.7 ls on document path exits 0 (document body treated as empty collection)" \
        "${EXSH[@]}" ls testcol:/hello.xml

    # T06.8 — --sort name: 'data.bin' (d) appears before 'stdin.xml' (s)
    _run "${EXSH[@]}" ls testcol --sort name
    _line_data=$(echo "${_LAST_OUTPUT}" | grep -n "data.bin"  | cut -d: -f1)
    _line_stdin=$(echo "${_LAST_OUTPUT}" | grep -n "stdin.xml" | cut -d: -f1)
    if [[ "${_line_data}" -lt "${_line_stdin}" ]]; then
        ok "T06.8 --sort name: data.bin before stdin.xml"
    else
        fail "T06.8 --sort name: expected data.bin (line ${_line_data}) before stdin.xml (line ${_line_stdin})"
    fi

    # T06.9 — --sort name --reverse: 'stdin.xml' before 'data.bin'
    _run "${EXSH[@]}" ls testcol --sort name --reverse
    _line_data=$(echo "${_LAST_OUTPUT}" | grep -n "data.bin"  | cut -d: -f1)
    _line_stdin=$(echo "${_LAST_OUTPUT}" | grep -n "stdin.xml" | cut -d: -f1)
    if [[ "${_line_stdin}" -lt "${_line_data}" ]]; then
        ok "T06.9 --sort name --reverse: stdin.xml before data.bin"
    else
        fail "T06.9 --sort name --reverse: expected stdin.xml (line ${_line_stdin}) before data.bin (line ${_line_data})"
    fi

    # T06.10 — --names-only: filenames present, properties absent
    assert_output "hello.xml" \
        "T06.10 --names-only shows filenames" \
        "${EXSH[@]}" ls testcol --names-only
    assert_output_absent "application/xml" \
        "T06.11 --names-only hides properties" \
        "${EXSH[@]}" ls testcol --names-only

    # T06.12 — --sort time: exits 0 and shows items
    assert_output "hello.xml" \
        "T06.12 --sort time lists items" \
        "${EXSH[@]}" ls testcol --sort time
}
