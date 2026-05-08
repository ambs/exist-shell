#!/usr/bin/env bash
# T11 — edit (modified, no-change, editor error, not-found)
# Sourced by scripts/e2e.sh — do not execute directly.

section_T11_edit() {
    step "T11 — edit"

    # T11.1 — create fake editor: replaces "world" with "eXist" using perl
    # (perl -i avoids BSD/GNU sed -i incompatibility)
    printf '#!/usr/bin/env bash\nperl -i -pe "s/world/eXist/" "$1"\n' \
        > "${TMPDIR_E2E}/fake_editor.sh"
    chmod +x "${TMPDIR_E2E}/fake_editor.sh"
    ok "T11.1 fake editor script created"

    # T11.2 — editor modifies file → re-uploaded
    assert_exit0 "T11.2 edit with modifying editor succeeds" \
        env EDITOR="${TMPDIR_E2E}/fake_editor.sh" "${EXSH[@]}" edit testcol:/hello.xml

    # T11.3 — verify change was persisted
    assert_output "eXist" \
        "T11.3 cat after edit shows updated content" \
        "${EXSH[@]}" cat testcol:/hello.xml

    # T11.4 — editor exits 0 without touching the file → No changes.
    assert_output "No changes." \
        "T11.4 edit with no-op editor prints No changes." \
        env EDITOR=true "${EXSH[@]}" edit testcol:/hello.xml

    # T11.5 — editor exits non-zero → error reported
    assert_output "editor exited with code" \
        "T11.5 edit with failing editor reports exit code" \
        env EDITOR=false "${EXSH[@]}" edit testcol:/hello.xml

    # T11.6 — document not found
    assert_output "not found in collection" \
        "T11.6 edit non-existent document fails" \
        env EDITOR=true "${EXSH[@]}" edit testcol:/nonexistent.xml

    # T11.7 — unknown collection nick
    assert_output "collection 'ghost' not found" \
        "T11.7 edit unknown nick fails" \
        env EDITOR=true "${EXSH[@]}" edit ghost:/hello.xml
}
